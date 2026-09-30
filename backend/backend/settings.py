"""
Django settings for the BioFusion AI backend.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw is not None else default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = _env(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = _env(
    "DJANGO_SECRET_KEY",
    "django-insecure-biofusion-ai-development-key",
)
DEBUG = _env_bool("DJANGO_DEBUG", True)

# Submission/prototype mode: the camera step is presented as iris capture,
# but the captured full frames are enrolled and verified with face + voice.
# Debug runs use the face+voice prototype by default while the frontend keeps
# its project-facing "Iris" labels. Tests and production stay strict by
# default; production startup also rejects an explicitly enabled prototype.
FACE_PRIMARY_CAPTURE_MODE = _env_bool(
    "FACE_PRIMARY_CAPTURE_MODE",
    DEBUG and "test" not in sys.argv,
)

ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS",
    ["127.0.0.1", "localhost", "10.0.2.2"],
)
if DEBUG and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("*")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "biometrics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"
ASGI_APPLICATION = "backend.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS",
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
)
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS", [])


REST_FRAMEWORK = {
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "biometrics.api.api_exception_handler",
}


API_PREFIX = "api/v1"
MODEL_CACHE_DIR = BASE_DIR / ".model_cache"
LOCAL_TRAINED_MODELS_DIR = BASE_DIR / "trained_models"
MODEL_DOWNLOAD_TIMEOUT_SECONDS = int(_env("MODEL_DOWNLOAD_TIMEOUT_SECONDS", "60"))
# Authentication is designed to run against the local Django service with no
# public-internet dependency. Set this to false only when intentionally
# provisioning missing model assets.
BIOMETRIC_OFFLINE_MODE = _env_bool("BIOMETRIC_OFFLINE_MODE", True)
REGISTRATION_CSV_PATH = Path(
    _env(
        "REGISTRATION_CSV_PATH",
        str(BASE_DIR.parent / "registration_exports" / "registrations.csv"),
    )
)

VOICE_MODEL_SOURCE = _env(
    "VOICE_MODEL_SOURCE",
    "speechbrain/spkrec-ecapa-voxceleb",
)
VOICE_MODEL_CACHE_DIR = Path(
    _env("VOICE_MODEL_CACHE_DIR", str(MODEL_CACHE_DIR / "voice"))
)
LOCAL_VOICE_MODEL_DIR = Path(
    _env("LOCAL_VOICE_MODEL_DIR", str(LOCAL_TRAINED_MODELS_DIR / "voice"))
)
IRIS_MODEL_CACHE_DIR = Path(
    _env("IRIS_MODEL_CACHE_DIR", str(MODEL_CACHE_DIR / "iris"))
)
IRIS_MODEL_URL = _env(
    "IRIS_MODEL_URL",
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
)
IRIS_MODEL_PATH = Path(
    _env(
        "IRIS_MODEL_PATH",
        str(IRIS_MODEL_CACHE_DIR / "face_landmarker.task"),
    )
)
LOCAL_IRIS_ONNX_MODEL_PATH = Path(
    _env(
        "LOCAL_IRIS_ONNX_MODEL_PATH",
        str(LOCAL_TRAINED_MODELS_DIR / "iris" / "iris_semseg_upp_scse_mobilenetv2.onnx"),
    )
)
# The bundled Worldcoin segmenter was trained with OpenCV's (width, height)
# resize convention at 640 x 480. Keep separate dimensions so the eye is not
# distorted into the old square tracking input.
IRIS_ONNX_INPUT_WIDTH = int(_env("IRIS_ONNX_INPUT_WIDTH", "640"))
IRIS_ONNX_INPUT_HEIGHT = int(_env("IRIS_ONNX_INPUT_HEIGHT", "480"))
# Eye ROIs preserve enough source detail that this smaller, encoder-compatible
# tensor is sufficient for live tracking.  Its 11:8 aspect ratio is also used
# for the source ROI, so the fitted ellipse is never stretched by preprocessing.
IRIS_TRACKING_INPUT_WIDTH = int(_env("IRIS_TRACKING_INPUT_WIDTH", "256"))
IRIS_TRACKING_INPUT_HEIGHT = int(_env("IRIS_TRACKING_INPUT_HEIGHT", "192"))
# Retained for the existing still-image quality path; live tracking uses the
# model's native rectangular input above.
IRIS_ONNX_INPUT_SIZE = int(_env("IRIS_ONNX_INPUT_SIZE", "320"))
VOICE_SAMPLE_RATE = int(_env("VOICE_SAMPLE_RATE", "16000"))
MAX_IRIS_UPLOAD_BYTES = int(_env("MAX_IRIS_UPLOAD_BYTES", str(12 * 1024 * 1024)))
MAX_VOICE_UPLOAD_BYTES = int(_env("MAX_VOICE_UPLOAD_BYTES", str(24 * 1024 * 1024)))
MAX_FACE_UPLOAD_BYTES = int(_env("MAX_FACE_UPLOAD_BYTES", str(12 * 1024 * 1024)))
MAX_TRACKING_FRAME_BYTES = int(
    _env("MAX_TRACKING_FRAME_BYTES", str(4 * 1024 * 1024))
)

# Secure defaults are enabled automatically when DEBUG is disabled. They can
# still be overridden for a deployment behind a TLS-terminating proxy.
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(
    _env("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG
)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
FACE_MODEL_ROOT = Path(
    _env("FACE_MODEL_ROOT", str(LOCAL_TRAINED_MODELS_DIR / "face"))
)
FACE_MODEL_NAME = _env("FACE_MODEL_NAME", "buffalo_l")

# Dedicated face anti-spoofing / liveness model (separate from the SCRFD face
# detector). Detection confidence is never treated as liveness evidence. When
# this asset is unavailable the face workflow fails closed instead of
# pretending liveness passed.
FACE_LIVENESS_MODEL_DIR = Path(
    _env("FACE_LIVENESS_MODEL_DIR", str(LOCAL_TRAINED_MODELS_DIR / "face"))
)
FACE_LIVENESS_MODEL_PATH = Path(
    _env(
        "FACE_LIVENESS_MODEL_PATH",
        str(FACE_LIVENESS_MODEL_DIR / "antispoof" / "minifasnet_v2.onnx"),
    )
)
FACE_LIVENESS_MODEL_NAME = _env("FACE_LIVENESS_MODEL_NAME", "MiniFASNet face anti-spoofing")
# Optional one-time provisioning URL. Only used when BIOMETRIC_OFFLINE_MODE is
# False; offline deployments must place the ONNX file locally.
FACE_LIVENESS_MODEL_URL = _env("FACE_LIVENESS_MODEL_URL", "")
FACE_LIVENESS_INPUT_SIZE = int(_env("FACE_LIVENESS_INPUT_SIZE", "80"))
FACE_LIVENESS_CROP_SCALE = _env_float("FACE_LIVENESS_CROP_SCALE", 2.7)
# Index of the "live" class in the classifier output. Decision basis: the
# A/B/C diagnostic (backend/diag_liveness.py) on a genuine webcam frame plus
# the upstream implementation (yakhyo/face-anti-spoofing onnx_inference.py),
# which feeds BGR, float32 RAW 0-255 pixels, NCHW, a 2.7 crop, and treats
# class index 1 as Real. The Hugging Face model card
# (garciafido/minifasnet-v2-anti-spoofing-onnx) documents /255 with class 0 =
# live, but the checkpoint's actual behaviour matches the upstream
# Silent-Face/MiniFASNet convention: on the SAME real face and crop, /255
# produced softmax [0.0004, 0.0061, 0.9935] (argmax 2) while raw 0-255
# produced [0.0071, 0.9799, 0.0131] (argmax 1), and the byte-exact
# upstream-replica pipeline agreed. This convention was NOT chosen because
# it produces PASS; it matches the checkpoint's observed behaviour.
FACE_LIVENESS_LIVE_INDEX = int(_env("FACE_LIVENESS_LIVE_INDEX", "1"))
# When True, the exact face crop fed to the liveness classifier is saved
# under MEDIA_ROOT/liveness_debug/ for manual inspection. Diagnostics only.
FACE_LIVENESS_DEBUG_SAVE_CROP = _env_bool("FACE_LIVENESS_DEBUG_SAVE_CROP", False)
FACE_LIVENESS_ACTIVATION = _env("FACE_LIVENESS_ACTIVATION", "softmax")
FACE_LIVENESS_THRESHOLD = _env_float("FACE_LIVENESS_THRESHOLD", 0.60)
# When True, registration and login require an affirmative liveness result; a
# missing model fails closed instead of silently skipping the anti-spoofing
# stage. Defaults to production-strict (required only when DEBUG is off) so a
# development machine without the anti-spoofing asset can still exercise the
# face/iris/voice pipeline. A positive spoof detection is always rejected
# regardless of this flag, and liveness is never reported as passed unless the
# dedicated model actually ran and returned a live score.
FACE_LIVENESS_REQUIRED = _env_bool("FACE_LIVENESS_REQUIRED", not DEBUG)
VOICE_MIN_SECONDS = _env_float("VOICE_MIN_SECONDS", 2.0)
VOICE_MAX_SECONDS = _env_float("VOICE_MAX_SECONDS", 15.0)
VOICE_QUALITY_THRESHOLD = _env_float("VOICE_QUALITY_THRESHOLD", 0.55)
VOICE_ACTIVITY_THRESHOLD = _env_float("VOICE_ACTIVITY_THRESHOLD", 0.35)
VOICE_SIMILARITY_THRESHOLD = _env_float("VOICE_SIMILARITY_THRESHOLD", 0.75)

FACE_DETECTION_THRESHOLD = _env_float("FACE_DETECTION_THRESHOLD", 0.65)
FACE_QUALITY_THRESHOLD = _env_float("FACE_QUALITY_THRESHOLD", 0.60)
FACE_SIMILARITY_THRESHOLD = _env_float("FACE_SIMILARITY_THRESHOLD", 0.70)
MIN_FACE_SAMPLES = int(_env("MIN_FACE_SAMPLES", "3"))
MIN_IRIS_SAMPLES = int(_env("MIN_IRIS_SAMPLES", "3"))
MIN_VOICE_SAMPLES = int(_env("MIN_VOICE_SAMPLES", "3"))
# Enrollment keeps several samples to build a stable template.  Authentication
# is intentionally a single live capture; the backend still validates and
# compares that capture against the enrolled template.
AUTH_FACE_SAMPLES = max(1, int(_env("AUTH_FACE_SAMPLES", "1")))
AUTH_IRIS_SAMPLES = max(1, int(_env("AUTH_IRIS_SAMPLES", "1")))
MIN_VOICE_SEGMENTS = int(_env("MIN_VOICE_SEGMENTS", "2"))
BIOMETRIC_TEMPLATE_KEYS = _env("BIOMETRIC_TEMPLATE_KEYS", "")

IRIS_QUALITY_THRESHOLD = _env_float("IRIS_QUALITY_THRESHOLD", 0.55)
IRIS_SIMILARITY_THRESHOLD = _env_float("IRIS_SIMILARITY_THRESHOLD", 0.78)

FUSION_VOICE_WEIGHT = _env_float("FUSION_VOICE_WEIGHT", 0.33)
FUSION_IRIS_WEIGHT = _env_float("FUSION_IRIS_WEIGHT", 0.33)
FUSION_FACE_WEIGHT = _env_float("FUSION_FACE_WEIGHT", 0.34)
FUSION_THRESHOLD = _env_float("FUSION_THRESHOLD", 0.80)
# Used only when one modality is temporarily unreliable: the reliable
# modality must exceed this (calibrated) confidence to carry the decision.
FUSION_SINGLE_MODALITY_FALLBACK_THRESHOLD = _env_float(
    "FUSION_SINGLE_MODALITY_FALLBACK_THRESHOLD", 0.72
)
# Detection confidence required before an iris measurement is treated as
# valid evidence (gates temporary segmentation failures, not identity).
IRIS_DETECTION_CONFIDENCE_THRESHOLD = _env_float(
    "IRIS_DETECTION_CONFIDENCE_THRESHOLD", 0.45
)
# A lower threshold than the visual "locked" state is intentionally avoided;
# three consecutive frames above this capture-readiness threshold are still
# required before a requested photo is taken.
IRIS_TRACKING_STABLE_CONFIDENCE = _env_float(
    "IRIS_TRACKING_STABLE_CONFIDENCE", 0.55
)
# JSON file written by `manage.py calibrate_fusion_thresholds` from genuine
# and impostor samples. Missing or invalid file -> settings defaults above.
FUSION_CALIBRATION_PATH = Path(
    _env(
        "FUSION_CALIBRATION_PATH",
        str(LOCAL_TRAINED_MODELS_DIR / "fusion_calibration.json"),
    )
)

DEVELOPMENT_THRESHOLDS = _env_bool("DEVELOPMENT_THRESHOLDS", DEBUG)
RETAIN_PROCESSED_UPLOADS = _env_bool("RETAIN_PROCESSED_UPLOADS", False)


if not DEBUG:
    # Never start a production process with development credentials, open
    # hosts/CORS, prototype face+voice-only authentication, or uncalibrated
    # thresholds. Failing at startup is safer than silently weakening auth.
    if SECRET_KEY.startswith("django-insecure-") or len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be a long random value when DJANGO_DEBUG=False."
        )
    if not _env("DJANGO_ALLOWED_HOSTS"):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must be explicitly configured in production."
        )
    if not _env("CORS_ALLOWED_ORIGINS"):
        raise ImproperlyConfigured(
            "CORS_ALLOWED_ORIGINS must be explicitly configured in production."
        )
    if not CSRF_TRUSTED_ORIGINS:
        raise ImproperlyConfigured(
            "CSRF_TRUSTED_ORIGINS must be explicitly configured in production."
        )
    if FACE_PRIMARY_CAPTURE_MODE:
        raise ImproperlyConfigured(
            "FACE_PRIMARY_CAPTURE_MODE must be False in production."
        )
    if not FACE_LIVENESS_REQUIRED:
        raise ImproperlyConfigured(
            "FACE_LIVENESS_REQUIRED must be True in production so face "
            "registration and login run the dedicated anti-spoofing model."
        )
    if DEVELOPMENT_THRESHOLDS:
        raise ImproperlyConfigured(
            "DEVELOPMENT_THRESHOLDS must be False in production."
        )
    if not str(BIOMETRIC_TEMPLATE_KEYS).strip():
        raise ImproperlyConfigured(
            "BIOMETRIC_TEMPLATE_KEYS must be configured in production."
        )




