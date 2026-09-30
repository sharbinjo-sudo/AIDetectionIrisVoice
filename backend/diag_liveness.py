"""MiniFASNet A/B/C diagnostic + production verification.

RESOLVED (2026-09): the A/B/C diagnostic fixed the integration conventions.
Production now feeds raw 0-255 float32 (no /255) and treats class index 1 as
Real, matching the upstream implementation
(yakhyo/face-anti-spoofing onnx_inference.py). Evidence on a genuine webcam
face, same crop:
    TEST A  production-OLD /255:     softmax=[0.0004, 0.0061, 0.9935] argmax=2
    TEST B  raw 0-255:               softmax=[0.0071, 0.9799, 0.0131] argmax=1
    TEST C  upstream-replica crop:   softmax=[0.0112, 0.9413, 0.0475] argmax=1
The Hugging Face model card documents /255 with class 0 = live, but the
checkpoint's actual behaviour matches upstream. The convention was NOT chosen
because it produces PASS.

What this script does now:
  1. ONE real frame -> SCRFD exactly one face -> ONE crop, saved for inspection.
  2. TEST A/B/C preprocessing comparison on that same crop (kept as evidence).
  3. PRODUCTION verification: the engine's own assess() runs on the same
     frame, printing raw logits, softmax, predicted class, live probability,
     spoof probability, and the deployed conventions; with
     FACE_LIVENESS_DEBUG_SAVE_CROP=True the exact classifier-input crop is
     saved under media/liveness_debug/ for inspection.

Usage:
    python diag_liveness.py                # one webcam frame
    python diag_liveness.py some_face.jpg  # analyse a still image instead
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402

django.setup()

import cv2  # noqa: E402
import numpy as np  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

START = time.perf_counter()


def step(message: str) -> None:
    print(f"[{time.perf_counter() - START:7.2f}s] {message}", flush=True)


def fail(message: str) -> int:
    print(f"\nERROR: {message}", flush=True)
    return 1


def capture_one_frame() -> np.ndarray | None:
    """The exact camera sequence confirmed working on this machine."""
    step("camera: cv2.VideoCapture(0, cv2.CAP_DSHOW)")
    capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not capture.isOpened():
        fail("cv2.VideoCapture(0, cv2.CAP_DSHOW) could not be opened.")
        return None
    step("camera: opened=True")

    ok, frame = capture.read()
    if not ok or frame is None:
        capture.release()
        fail("capture.read() returned no frame.")
        return None
    step(f"camera: first real frame shape={frame.shape}")

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    # Warm-up: the first DSHOW frames can be stale/unexposed, so grab a few
    # and keep the last (diagnostic-only; production captures a live stream).
    frame = None
    for attempt in range(15):
        ok, frame = capture.read()
        if not ok or frame is None:
            capture.release()
            fail("capture.read() after setting 640x480 returned no frame.")
            return None
        if attempt < 14:
            time.sleep(0.05)
    if frame is None:
        capture.release()
        fail("capture.read() after setting 640x480 returned no frame.")
        return None
    step(f"camera: warm-up complete, frame shape={frame.shape}")

    capture.release()
    step("camera: released")
    return frame


def numpy_softmax(values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    exponentials = np.exp(array - array.max())
    return exponentials / exponentials.sum()


def forward_blob(liveness, blob) -> list[float]:
    with liveness._lock:
        liveness._net.setInput(blob)
        return np.asarray(liveness._net.forward()).reshape(-1).tolist()


def app_probabilities(liveness, raw_logits) -> list[float]:
    """The engine's exact activation handling (_probabilities)."""
    return liveness._probabilities(raw_logits)


def report_test(
    label: str,
    blob: np.ndarray,
    raw_logits: list[float],
    scale_note: str,
) -> None:
    probabilities = numpy_softmax(raw_logits)
    argmax = int(np.argmax(probabilities))
    print(f"\n----- {label} ({scale_note}) -----")
    print(f"tensor min/max:   {float(blob.min()):.6f} / {float(blob.max()):.6f}")
    print(f"tensor dtype/shape: {blob.dtype} {blob.shape}")
    print(f"raw logits:       {[round(v, 4) for v in raw_logits]}")
    print(f"softmax:          {[round(float(v), 4) for v in probabilities]}")
    print(f"argmax class:     {argmax}")


def upstream_crop(image: np.ndarray, bbox_xyxy: list[float], scale: float, size: int) -> np.ndarray:
    """Byte-exact replica of yakhyo/face-anti-spoofing onnx_inference.py.

    _xyxy2xywh -> _crop_face (scale = min((H-1)/h, (W-1)/w, scale), centred,
    clamped, no padding) -> float32 (NO /255) -> CHW -> NCHW.
    """
    x1, y1, x2, y2 = bbox_xyxy
    x, y, box_w, box_h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
    src_h, src_w = image.shape[:2]
    used = min((src_h - 1) / box_h, (src_w - 1) / box_w, scale)
    new_w = box_w * used
    new_h = box_h * used
    center_x = x + box_w / 2
    center_y = y + box_h / 2
    x1c = max(0, int(center_x - new_w / 2))
    y1c = max(0, int(center_y - new_h / 2))
    x2c = min(src_w - 1, int(center_x + new_w / 2))
    y2c = min(src_h - 1, int(center_y + new_h / 2))
    cropped = image[y1c : y2c + 1, x1c : x2c + 1]
    face = cv2.resize(cropped, (size, size)).astype(np.float32)
    face = np.transpose(face, (2, 0, 1))
    return np.expand_dims(face, axis=0), used


def production_verification(liveness, frame, bbox) -> int:
    """Run the deployed assess() on the SAME frame and report full diagnostics."""
    from django.conf import settings

    step("[7/6] PRODUCTION verification: engine.assess() on the same frame")
    print(
        "deployed conventions: BGR, 80x80, NCHW, raw 0-255 float32 "
        f"(no /255), crop scale {settings.FACE_LIVENESS_CROP_SCALE}, "
        f"live_index={settings.FACE_LIVENESS_LIVE_INDEX}, "
        f"threshold={settings.FACE_LIVENESS_THRESHOLD}"
    )
    result = liveness.assess(frame, [float(v) for v in bbox])
    print(f"raw logits:        see 'face liveness diagnostic' log line above")
    print(
        f"predicted class:   (log line above; live_index="
        f"{settings.FACE_LIVENESS_LIVE_INDEX} = Real)"
    )
    print(f"live probability:  {result.live_score:.4f}")
    print(f"spoof probability: {result.spoof_score:.4f}")
    print(f"threshold:         {result.threshold} (unchanged)")
    print(f"status:            {result.status}")
    print(f"passed:            {result.passed}")
    print(f"reason:            {result.reason_code}")
    debug_dir = Path(settings.MEDIA_ROOT) / "liveness_debug"
    if settings.FACE_LIVENESS_DEBUG_SAVE_CROP:
        saved = sorted(debug_dir.glob("liveness_crop_*.jpg"))
        if saved:
            print(f"saved crops:       {saved[-2:]}")
    else:
        print(
            "saved crops:       set FACE_LIVENESS_DEBUG_SAVE_CROP=True to save "
            "the exact classifier-input crop under media/liveness_debug/"
        )
    return 0 if result.status == "LIVE" else 2


def main() -> int:
    from django.conf import settings

    from biometrics.services.face_engine import get_face_engine
    from biometrics.services.face_liveness import get_face_liveness_engine

    step("[1/6] loading engines")
    liveness = get_face_liveness_engine()
    health = liveness.health()
    if not health["ready"]:
        return fail(f"MODEL UNAVAILABLE: {health['detail']}")
    detector = get_face_engine()
    if not detector.ready:
        return fail(f"SCRFD detector unavailable: {detector._load_error}")

    still_path = sys.argv[1] if len(sys.argv) > 1 else None
    if still_path is not None:
        frame = cv2.imread(still_path)
        if frame is None:
            return fail(f"could not read still image: {still_path}")
    else:
        step("[2/6] capturing one real webcam frame")
        frame = capture_one_frame()
        if frame is None:
            return 1

    step("[3/6] SCRFD on the frame (production path)")
    faces = detector._detect_faces(frame)
    scores = [round(float(f["score"]), 4) for f in faces]
    boxes = [[round(float(v), 1) for v in f["bbox"]] for f in faces]
    step(f"SCRFD: faces={len(faces)} scores={scores} bboxes={boxes}")
    if len(faces) != 1:
        return fail(
            f"SCRFD found {len(faces)} face(s); the A/B test needs exactly 1."
        )
    bbox = [float(v) for v in faces[0]["bbox"]]
    detection_score = float(faces[0]["score"])

    # ----------------------------------------------------------------------
    # ONE crop for both tests: the engine's reference clamped crop, saved.
    # ----------------------------------------------------------------------
    crop = liveness._square_face_crop(frame, bbox)
    if crop is None:
        return fail(f"face crop failed for bbox={bbox}")
    size = int(settings.FACE_LIVENESS_INPUT_SIZE)
    tmp_dir = Path(settings.MEDIA_ROOT) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    frame_path = tmp_dir / "ab_diag_frame.jpg"
    crop_path = tmp_dir / "ab_face_crop.jpg"
    resized_path = tmp_dir / "ab_face_crop_80x80.jpg"
    cv2.imwrite(str(frame_path), frame)
    cv2.imwrite(str(crop_path), crop)
    resized = cv2.resize(crop, (size, size))
    cv2.imwrite(str(resized_path), resized)
    step(f"[3/6] frame+crop saved -> {frame_path.name}, {crop_path.name}, {resized_path.name}")

    # ----------------------------------------------------------------------
    # [4/6] TEST A vs TEST B on the SAME crop.
    # ----------------------------------------------------------------------
    step("[4/6] TEST A (production: /255) vs TEST B (upstream: raw 0-255)")
    blob_a = cv2.dnn.blobFromImage(
        resized,
        scalefactor=1.0 / 255.0,
        size=(size, size),
        mean=(0.0, 0.0, 0.0),
        swapRB=False,
    )
    logits_a = forward_blob(liveness, blob_a)
    report_test("TEST A  production preprocessing", blob_a, logits_a, "BGR /255, NCHW")

    blob_b = cv2.dnn.blobFromImage(
        resized,
        scalefactor=1.0,
        size=(size, size),
        mean=(0.0, 0.0, 0.0),
        swapRB=False,
    )
    logits_b = forward_blob(liveness, blob_b)
    report_test("TEST B  upstream preprocessing", blob_b, logits_b, "BGR raw 0-255, NCHW")

    # ----------------------------------------------------------------------
    # [5/6] Upstream-replica pipeline (crop + preprocess in one shot).
    # ----------------------------------------------------------------------
    step("[5/6] upstream-replica crop+preprocess (int/int clamped crop, no /255)")
    blob_c, used_scale_c = upstream_crop(frame, bbox, float(settings.FACE_LIVENESS_CROP_SCALE), size)
    logits_c = forward_blob(liveness, blob_c)
    report_test("TEST C  full upstream replica", blob_c, logits_c, "BGR raw 0-255, NCHW, int crop")

    # ----------------------------------------------------------------------
    # Class-order report: NO mapping chosen, NO result forced.
    # ----------------------------------------------------------------------
    step("[6/6] class-order interpretation report (no decision made here)")
    probs_a = numpy_softmax(logits_a)
    probs_b = numpy_softmax(logits_b)
    print("\n===== CLASS-ORDER DIAGNOSTIC (report only) =====")
    print(f"configured FACE_LIVENESS_LIVE_INDEX: {settings.FACE_LIVENESS_LIVE_INDEX}")
    for name, probs in (("TEST A (/255)", probs_a), ("TEST B (raw 0-255)", probs_b)):
        argmax = int(np.argmax(probs))
        print(f"\n{name}: softmax={[round(float(v), 4) for v in probs]} argmax={argmax}")
        print(
            f"  interpretation A) [live, print, replay]: "
            f"live_prob={probs[0]:.4f} -> "
            f"{'LIVE' if probs[0] >= float(settings.FACE_LIVENESS_THRESHOLD) else 'SPOOF'}"
        )
        print(
            f"  interpretation B) class 1 = Real convention: "
            f"real_prob(class1)={probs[1]:.4f} -> "
            f"{'LIVE' if probs[1] >= float(settings.FACE_LIVENESS_THRESHOLD) else 'SPOOF'}"
        )
    print(
        "\nNOTE: which interpretation is correct can only be settled by "
        "calibration evidence (e.g. score a known photo-of-a-print attack "
        "and a known live face through BOTH preprocessing variants and see "
        "which class lights up), not by preferring a reference."
    )

    # ----------------------------------------------------------------------
    # Crop-pipeline comparison against the upstream reference.
    # ----------------------------------------------------------------------
    box_w, box_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    engine_scale = min(
        (frame.shape[0] - 1) / box_h,
        (frame.shape[1] - 1) / box_w,
        float(settings.FACE_LIVENESS_CROP_SCALE),
    )
    print("\n===== CROP PIPELINE COMPARISON (ours vs upstream) =====")
    print(f"bbox (x1,y1,x2,y2):   [{bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f}]")
    print(f"bbox conversion:      ours xyxy->xywh(float) | upstream int(x1),int(y1),int(x2-x1),int(y2-y1)")
    print(f"scale formula:        identical: min((H-1)/box_h, (W-1)/box_w, 2.7)")
    print(
        f"effective scale:      ours (float bbox)={engine_scale:.4f} | "
        f"upstream (int bbox)={used_scale_c:.4f}"
    )
    print(f"crop bounds:          both centred on face, clamped to image, no padding")
    print(f"crop dimensions:      {crop.shape[1]}x{crop.shape[0]} (ours) | int-bbox replica differs only by <=1px rounding")
    print(f"resize:               both cv2.resize direct to {size}x{size}")
    print("colour order:         both BGR (swapRB=False here; upstream keeps BGR too)")
    print(
        "normalization:        DIFFERENT - ours /255 (0..1), upstream raw 0..255 "
        "(blobFromImage scalefactor 1.0)"
    )
    print(f"tensor layout:        both NCHW float32 {blob_a.shape[2:]}")
    print(f"SCRFD score:          {detection_score:.4f}")

    exit_code = production_verification(liveness, frame, bbox)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
