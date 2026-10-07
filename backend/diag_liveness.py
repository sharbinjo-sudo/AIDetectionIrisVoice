"""MiniFASNetV2 convention + live-vs-spoof diagnostic.

Purpose
-------
Decide — with evidence, not convenience — which inference convention the
deployed MiniFASNetV2 checkpoint actually implements, and whether the model
alone separates live faces from photo/screen/print attacks.

For EVERY sample (genuine webcam face, phone photo, printed photo, replayed
video, or any still image) the script:

1. verifies the exact ONNX model hash on this machine,
2. runs the PRODUCTION SCRFD detector and takes the PRODUCTION face crop
   (biometrics.services.face_liveness.FaceLivenessEngine._square_face_crop),
   byte-compared against the crop production itself persists via
   FACE_LIVENESS_DEBUG_SAVE_CROP,
3. runs the SAME 80x80 crop through both candidate pipelines:
   TEST A: BGR float32 / 255, class order [live, print, replay]  (model card)
   TEST B: BGR float32 raw 0-255, class 1 = Real                  (upstream)
4. records raw logits, softmax, predicted class, live probability, spoof
   probability and the final decision for BOTH pipelines and BOTH class
   mappings, then summarises the live-vs-spoof separation per pipeline.

The pipeline is NOT selected because a genuine face passes: the decision
weighs the reference implementation (provenance) AND the observed
live-vs-spoof separation.

Usage:
    python diag_liveness.py                          # one webcam frame
    python diag_liveness.py img.jpg [img2.jpg ...]   # still images
    python diag_liveness.py --capture 4 12           # 4 webcam frames, 12s apart
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

EXPECTED_MODEL_SHA256 = "d7b3cd9ba8a7ceb13baa8c4720902e27ca3112eff52f926c08804af6b6eecc7b"
THRESHOLD = None  # filled from settings in main()


def step(message: str) -> None:
    print(message, flush=True)


def fail(message: str) -> int:
    print(f"\nERROR: {message}", flush=True)
    return 1


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def numpy_softmax(values) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    exponentials = np.exp(array - array.max())
    return exponentials / exponentials.sum()


def capture_one_frame() -> np.ndarray | None:
    """The camera sequence confirmed working on this machine."""
    capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not capture.isOpened():
        fail("cv2.VideoCapture(0, cv2.CAP_DSHOW) could not be opened.")
        return None
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frame = None
    for _ in range(15):
        ok, frame = capture.read()
        if not ok or frame is None:
            capture.release()
            fail("capture.read() returned no frame.")
            return None
        time.sleep(0.05)
    capture.release()
    return frame


def forward_blob(liveness, blob) -> list[float]:
    with liveness._lock:
        liveness._net.setInput(blob)
        return np.asarray(liveness._net.forward()).reshape(-1).tolist()


def evaluate_sample(
    liveness,
    detector,
    label: str,
    frame: np.ndarray,
    out_dir: Path,
    threshold: float,
) -> dict | None:
    """Run both pipelines on the production crop of one frame."""
    faces = detector._detect_faces(frame)
    if len(faces) != 1:
        step(
            f"[{label}] SCRFD found {len(faces)} faces — sample skipped "
            "(diagnostic requires exactly one)."
        )
        return None
    bbox = [float(v) for v in faces[0]["bbox"]]
    crop = liveness._square_face_crop(frame, bbox)
    if crop is None:
        step(f"[{label}] face crop failed for bbox={bbox}")
        return None
    size = int(settings.FACE_LIVENESS_INPUT_SIZE)
    resized = cv2.resize(crop, (size, size))

    crop_path = out_dir / f"crop_{label}.jpg"
    cv2.imwrite(str(crop_path), crop)
    crop_hash = sha256_bytes(crop.tobytes())

    # Production-crop equality proof: run the production assess() with the
    # debug-crop flag enabled and byte-compare the persisted 80x80 model
    # input with the diagnostic's own resized crop.
    from biometrics.services.face_liveness import FaceLivenessEngine

    debug_dir = Path(settings.MEDIA_ROOT) / "liveness_debug"
    saved_before = set(debug_dir.glob("liveness_crop_*_80x80.jpg"))
    old_flag = settings.FACE_LIVENESS_DEBUG_SAVE_CROP
    try:
        settings.FACE_LIVENESS_DEBUG_SAVE_CROP = True
        production_result = liveness.assess(frame, bbox)
    finally:
        settings.FACE_LIVENESS_DEBUG_SAVE_CROP = old_flag
    saved = sorted(set(debug_dir.glob("liveness_crop_*_80x80.jpg")) - saved_before)
    diagnostic_input_file = debug_dir / f"diag_crop_{label}_80x80.jpg"
    cv2.imwrite(str(diagnostic_input_file), resized)
    # Byte-compare IDENTICALLY-ENCODED files (cv2.imwrite is deterministic for
    # identical inputs on the same OpenCV build): production's persisted 80x80
    # model input vs the diagnostic's own resize of the production crop.
    production_input_hash = sha256_bytes(saved[-1].read_bytes()) if saved else "MISSING"
    diagnostic_input_hash = sha256_bytes(diagnostic_input_file.read_bytes())
    crop_equal = production_input_hash == diagnostic_input_hash

    results = {}
    for name, scalefactor, live_index, mapping in (
        ("A(/255)", 1.0 / 255.0, 0, "[live, print, replay]"),
        ("B(raw)", 1.0, 1, "[fake, Real, fake]"),
    ):
        blob = cv2.dnn.blobFromImage(
            resized,
            scalefactor=scalefactor,
            size=(size, size),
            mean=(0.0, 0.0, 0.0),
            swapRB=False,
        )
        logits = forward_blob(liveness, blob)
        probs = numpy_softmax(logits)
        predicted = int(np.argmax(probs))
        live_prob = float(probs[live_index])
        spoof_prob = float(max(p for i, p in enumerate(probs) if i != live_index))
        results[name] = {
            "mapping": mapping,
            "logits": [round(v, 4) for v in logits],
            "softmax": [round(float(v), 4) for v in probs],
            "predicted_class": predicted,
            "live_index": live_index,
            "live_prob": round(live_prob, 4),
            "spoof_prob": round(spoof_prob, 4),
            "decision": "LIVE" if live_prob >= threshold else "SPOOF",
        }

    production_input_hash_short = production_input_hash[:12]
    print(
        f"\n===== SAMPLE: {label} =====\n"
        f"SCRFD score:        {float(faces[0]['score']):.4f}\n"
        f"crop:               {crop_path.name} {crop.shape[1]}x{crop.shape[0]} "
        f"sha256[:12]={crop_hash[:12]}\n"
        f"crop equality:      production-input={production_input_hash_short} "
        f"diagnostic-input={diagnostic_input_hash[:12]} "
        f"-> {'IDENTICAL' if crop_equal else 'DIFFERENT (!!)'}\n"
        f"production result:  {production_result.status} "
        f"live={production_result.live_score:.4f} spoof={production_result.spoof_score:.4f}"
    )
    for name, data in results.items():
        print(
            f"TEST {name}: logits={data['logits']} softmax={data['softmax']} "
            f"predicted={data['predicted_class']} live_prob={data['live_prob']} "
            f"spoof_prob={data['spoof_prob']} decision={data['decision']} "
            f"(mapping {data['mapping']})"
        )
    return {
        "label": label,
        "A": results["A(/255)"],
        "B": results["B(raw)"],
        "production": {
            "status": production_result.status,
            "live": round(production_result.live_score, 4),
            "spoof": round(production_result.spoof_score, 4),
        },
        "crop_equal": crop_equal,
    }


def main() -> int:
    global THRESHOLD
    from biometrics.services.face_engine import get_face_engine
    from biometrics.services.face_liveness import get_face_liveness_engine

    THRESHOLD = float(settings.FACE_LIVENESS_THRESHOLD)
    model_path = Path(settings.FACE_LIVENESS_MODEL_PATH)
    if not model_path.exists():
        return fail(f"liveness model missing: {model_path}")
    model_hash = sha256_bytes(model_path.read_bytes())
    step(f"model: {model_path.name}")
    step(f"model sha256: {model_hash}")
    step(f"expected     : {EXPECTED_MODEL_SHA256}")
    step(f"hash match   : {'YES' if model_hash == EXPECTED_MODEL_SHA256 else 'NO (!!)'}")

    liveness = get_face_liveness_engine()
    if not liveness.health()["ready"]:
        return fail(f"liveness engine not ready: {liveness.health()['detail']}")
    detector = get_face_engine()
    if not detector.ready:
        return fail(f"SCRFD detector unavailable: {detector._load_error}")

    args = [a for a in sys.argv[1:] if a != "--capture"]
    capture_mode = "--capture" in sys.argv[1:]
    out_dir = Path(settings.MEDIA_ROOT) / "tmp" / "ab_samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    samples: list[tuple[str, np.ndarray]] = []
    if capture_mode:
        count = int(args[0]) if args else 4
        interval = float(args[1]) if len(args) > 1 else 12.0
        labels = ["1_live_face", "2_phone_photo", "3_printed_photo", "4_replay_video"]
        for index in range(count):
            label = labels[index] if index < len(labels) else f"{index + 1}_sample"
            step(f"capturing sample '{label}' in {interval:.0f}s ...")
            time.sleep(interval)
            frame = capture_one_frame()
            if frame is None:
                return 1
            path = out_dir / f"frame_{label}.jpg"
            cv2.imwrite(str(path), frame)
            samples.append((label, frame))
            step(f"captured -> {path}")
    else:
        if not args:
            step("capturing one live webcam frame ...")
            frame = capture_one_frame()
            if frame is None:
                return 1
            cv2.imwrite(str(out_dir / "frame_live.jpg"), frame)
            samples.append(("live", frame))
        for arg in args:
            path = Path(arg)
            frame = cv2.imread(str(path))
            if frame is None:
                return fail(f"could not read image: {path}")
            samples.append((path.stem, frame))

    records = []
    for label, frame in samples:
        record = evaluate_sample(liveness, detector, label, frame, out_dir, THRESHOLD)
        if record:
            records.append(record)

    # ---- Separation summary: live-vs-spoof separation per pipeline --------
    step("\n===== CONVENTION / SEPARATION SUMMARY (threshold=%.2f) =====" % THRESHOLD)
    genuine = [r for r in records if "live" in r["label"].lower()]
    attacks = [r for r in records if "live" not in r["label"].lower()]
    for name in ("A", "B"):
        live_probs = [r[name]["live_prob"] for r in records]
        genuine_pass = sum(1 for r in genuine if r[name]["decision"] == "LIVE")
        attack_blocked = sum(1 for r in attacks if r[name]["decision"] == "SPOOF")
        margin = ""
        if genuine and attacks:
            min_live = min(r[name]["live_prob"] for r in genuine)
            max_attack = max(r[name]["live_prob"] for r in attacks)
            margin = f" | separation margin={max_attack - min_live:+.4f}"
        step(
            f"TEST {name}: genuine LIVE {genuine_pass}/{len(genuine)} | "
            f"attacks blocked {attack_blocked}/{len(attacks)}{margin}"
        )
    step(
        "\nDecision rule: select the convention supported by the reference "
        "implementation AND the observed live-vs-spoof separation — never "
        "merely the one that lets a genuine face pass."
    )
    if records and not all(r["crop_equal"] for r in records):
        step("WARNING: production vs diagnostic crop mismatch detected!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
