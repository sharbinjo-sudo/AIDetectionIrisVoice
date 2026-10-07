"""Temporal, challenge-based liveness (randomized action verification).

A single-frame PAD verdict is supporting evidence, never proof of liveness:
the A/B diagnostic (backend/diag_liveness.py) shows the deployed MiniFASNetV2
checkpoint separates a genuine face from photo/print/replay attacks on the
captured sample set, but a single-frame classifier can be defeated by a
high-quality attack and must not be the only gate. Registration and login
therefore additionally require the user to perform a RANDOM action — blink,
turn the head left or right — verified over multiple consecutive webcam
frames.

Privacy: no video and no raw frames are stored. Frames exist only in memory
for the duration of per-frame feature extraction and are released
immediately afterwards. The challenge session retains only numeric signal
samples (floats), the action name, and the verdict.

Direction convention: ``yaw`` is measured in RAW (unmirrored) camera
coordinates as ``(nose_x - eyes_mid_x) / eye_distance``. A positive yaw
means the nose tip moved toward the camera's right, which corresponds to
the user turning their head to their OWN left.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.core.cache import cache

from .exceptions import BiometricValidationError

ACTIONS = ("BLINK", "TURN_LEFT", "TURN_RIGHT")
TOKEN_SALT = "liveness-challenge"


def _ttl() -> int:
    return int(getattr(settings, "FACE_CHALLENGE_SESSION_TTL", 180))


def _token_max_age() -> int:
    return int(getattr(settings, "FACE_CHALLENGE_TOKEN_MAX_AGE", 600))


def _min_frames() -> int:
    return int(getattr(settings, "FACE_CHALLENGE_MIN_FRAMES", 6))


def _motion_threshold() -> float:
    return float(getattr(settings, "FACE_CHALLENGE_MOTION_THRESHOLD", 2.0))


def _motion_frames_required() -> int:
    return int(getattr(settings, "FACE_CHALLENGE_MOTION_FRAMES", 2))


def _open_threshold() -> float:
    return float(getattr(settings, "FACE_CHALLENGE_OPEN_THRESHOLD", 0.16))


def _closed_threshold() -> float:
    return float(getattr(settings, "FACE_CHALLENGE_CLOSED_THRESHOLD", 0.09))


def _closed_frames_required() -> int:
    return int(getattr(settings, "FACE_CHALLENGE_CLOSED_FRAMES", 2))


def _turn_threshold() -> float:
    return float(getattr(settings, "FACE_CHALLENGE_TURN_THRESHOLD", 0.18))


def _turn_frames_required() -> int:
    return int(getattr(settings, "FACE_CHALLENGE_TURN_FRAMES", 2))


@dataclass(frozen=True)
class FrameSignal:
    """Per-frame liveness signals. No pixels are retained here."""

    eye_openness: float  # eye aspect ratio, dimensionless
    yaw: float  # normalized nose offset (-1..1), see module docstring
    motion: float  # mean abs grayscale diff vs the previous frame


def _key(challenge_id: str) -> str:
    return f"liveness_challenge:{challenge_id}"


def create_challenge() -> dict:
    """Create a randomized challenge session (server-side state, TTL-bound)."""
    action = secrets.choice(ACTIONS)
    challenge_id = secrets.token_urlsafe(24)
    cache.set(
        _key(challenge_id),
        {"action": action, "verified": False, "consumed": False},
        _ttl(),
    )
    return {
        "challenge_id": challenge_id,
        "action": action,
        "expires_in": _ttl(),
        "instructions": {
            "BLINK": "Blink naturally while facing the camera.",
            "TURN_LEFT": "Slowly turn your head to your LEFT and hold briefly.",
            "TURN_RIGHT": "Slowly turn your head to your RIGHT and hold briefly.",
        }[action],
    }


def _session(challenge_id: str) -> dict | None:
    return cache.get(_key(challenge_id))


def verify_challenge_frames(challenge_id: str, frames: list) -> dict:
    """Verify an action over a sequence of frames; raw frames are not stored.

    ``frames`` is a list of decoded BGR images held only in memory by the
    caller; they are dereferenced as soon as signal extraction completes.
    """
    session = _session(challenge_id)
    if session is None:
        return {
            "verified": False,
            "reason": "CHALLENGE_EXPIRED",
            "message": "The liveness challenge expired. Start a new one.",
        }
    if len(frames) < _min_frames():
        return {
            "verified": False,
            "reason": "INSUFFICIENT_FRAMES",
            "message": (
                f"At least {_min_frames()} consecutive frames are required "
                "for the liveness challenge."
            ),
        }

    signals = extract_signals(frames)
    del frames[:]  # release raw frames immediately after extraction

    verdict = evaluate_action(session["action"], signals)
    if verdict["verified"]:
        session["verified"] = True
        cache.set(_key(challenge_id), session, _ttl())
        verdict["challenge_token"] = signing.dumps(
            {"cid": challenge_id, "act": session["action"]},
            salt=TOKEN_SALT,
        )
    return verdict


def evaluate_action(action: str, signals: list[FrameSignal]) -> dict:
    """Pure action verification over extracted signals (no pixels involved)."""
    fail = {
        "verified": False,
        "reason": "LIVENESS_CHALLENGE_FAILED",
        "message": "The requested liveness action could not be verified.",
    }
    if action not in ACTIONS:
        fail["reason"] = "UNKNOWN_ACTION"
        return fail
    if len(signals) < _min_frames():
        fail["reason"] = "INSUFFICIENT_FRAMES"
        return fail

    # Anti static-replay: a repeated still image produces no inter-frame
    # motion, no matter how the single frames look.
    motion_frames = sum(1 for s in signals[1:] if s.motion > _motion_threshold())
    if motion_frames < _motion_frames_required():
        fail["reason"] = "STATIC_SEQUENCE"
        fail["message"] = (
            "The frames appear to be a repeated still image; live motion is "
            "required."
        )
        return fail

    performed = 0
    if action == "BLINK":
        opened = False
        closed_run = 0
        for signal in signals:
            if signal.eye_openness >= _open_threshold():
                opened = True
                closed_run = 0
            elif signal.eye_openness <= _closed_threshold():
                closed_run += 1
                if opened and closed_run >= _closed_frames_required():
                    performed = closed_run
                    break
        if performed < _closed_frames_required():
            fail["reason"] = "BLINK_NOT_DETECTED"
            fail["message"] = (
                "No blink was detected. Look at the camera and blink once."
            )
            return fail
    else:
        direction = 1.0 if action == "TURN_LEFT" else -1.0
        best_run = 0
        run = 0
        for signal in signals:
            if direction * signal.yaw >= _turn_threshold():
                run += 1
                best_run = max(best_run, run)
            else:
                run = 0
        if best_run < _turn_frames_required():
            fail["reason"] = "TURN_NOT_DETECTED"
            fail["message"] = (
                "The requested head turn was not detected. Turn your head "
                "slowly to your "
                f"{'LEFT' if action == 'TURN_LEFT' else 'RIGHT'}."
            )
            return fail
        performed = best_run

    return {
        "verified": True,
        "reason": "LIVENESS_CHALLENGE_OK",
        "message": "Liveness challenge verified.",
        "action": action,
        "frames": len(signals),
        "motion_frames": motion_frames,
        "action_frames": performed,
    }


def consume_verified_challenge(token: str | None) -> str:
    """Consume a signed, verified challenge token exactly once.

    Raises ``BiometricValidationError`` when the token is missing, invalid,
    expired, not verified, or already used. Returns the performed action.
    """
    if not token:
        raise BiometricValidationError(
            "A verified liveness challenge is required for this operation."
        )
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=_token_max_age())
        challenge_id = str(payload["cid"])
        action = str(payload["act"])
    except Exception as exc:
        raise BiometricValidationError(
            "The liveness challenge token is invalid or expired."
        ) from exc
    session = _session(challenge_id)
    if session is None or not session.get("verified") or session.get("consumed"):
        raise BiometricValidationError(
            "The liveness challenge was not verified, has expired, or was "
            "already used."
        )
    session["consumed"] = True
    cache.set(_key(challenge_id), session, _ttl())
    return action


def extract_signals(frames: list) -> list[FrameSignal]:
    """Compute per-frame signals; raw frames are released by the caller."""
    import cv2
    import numpy as np

    from .engines import get_iris_engine

    engine = get_iris_engine()
    signals: list[FrameSignal] = []
    previous_gray = None
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        motion = 0.0 if previous_gray is None else float(
            np.mean(np.abs(gray - previous_gray))
        )
        previous_gray = gray
        landmarks = engine.face_landmarks(frame)
        signals.append(signals_from_landmarks(landmarks, motion))
    return signals


def signals_from_landmarks(landmarks, motion: float) -> FrameSignal:
    """Pure landmark -> signal math (MediaPipe 478-point normalized coords)."""
    if not landmarks or len(landmarks) <= 386:
        return FrameSignal(eye_openness=0.0, yaw=0.0, motion=motion)
    try:
        left = {
            "outer_x": landmarks[33].x,
            "inner_x": landmarks[133].x,
            "upper_y": landmarks[159].y,
            "lower_y": landmarks[145].y,
        }
        right = {
            "outer_x": landmarks[263].x,
            "inner_x": landmarks[362].x,
            "upper_y": landmarks[386].y,
            "lower_y": landmarks[374].y,
        }
        ear_left = abs(left["upper_y"] - left["lower_y"]) / max(
            abs(left["outer_x"] - left["inner_x"]), 1e-6
        )
        ear_right = abs(right["upper_y"] - right["lower_y"]) / max(
            abs(right["outer_x"] - right["inner_x"]), 1e-6
        )
        left_cx = (left["outer_x"] + left["inner_x"]) / 2
        right_cx = (right["outer_x"] + right["inner_x"]) / 2
        eyes_mid_x = (left_cx + right_cx) / 2
        eye_distance = max(abs(right_cx - left_cx), 1e-6)
        nose_x = landmarks[1].x
        yaw = (nose_x - eyes_mid_x) / eye_distance
    except (AttributeError, IndexError, ZeroDivisionError):
        return FrameSignal(eye_openness=0.0, yaw=0.0, motion=motion)
    return FrameSignal(
        eye_openness=max(ear_left, ear_right), yaw=yaw, motion=motion
    )
