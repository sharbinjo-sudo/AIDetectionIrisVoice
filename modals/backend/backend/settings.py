"""
Django settings for the BioFusion AI backend.
"""

from __future__ import annotations

import os
from pathlib import Path


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
LOCAL_PRETRAINED_MODELS_DIR = BASE_DIR / "pretrained_models"
MODEL_DOWNLOAD_TIMEOUT_SECONDS = int(_env("MODEL_DOWNLOAD_TIMEOUT_SECONDS", "60"))

VOICE_MODEL_SOURCE = _env(
    "VOICE_MODEL_SOURCE",
    "speechbrain/spkrec-ecapa-voxceleb",
)
VOICE_MODEL_CACHE_DIR = Path(
    _env("VOICE_MODEL_CACHE_DIR", str(MODEL_CACHE_DIR / "voice"))
)
LOCAL_VOICE_MODEL_DIR = Path(
    _env("LOCAL_VOICE_MODEL_DIR", str(LOCAL_PRETRAINED_MODELS_DIR / "voice"))
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
        str(LOCAL_PRETRAINED_MODELS_DIR / "iris" / "iris_semseg_upp_scse_mobilenetv2.onnx"),
    )
)
IRIS_ONNX_INPUT_SIZE = int(_env("IRIS_ONNX_INPUT_SIZE", "320"))
VOICE_SAMPLE_RATE = int(_env("VOICE_SAMPLE_RATE", "16000"))
VOICE_MIN_SECONDS = _env_float("VOICE_MIN_SECONDS", 2.0)
VOICE_MAX_SECONDS = _env_float("VOICE_MAX_SECONDS", 15.0)
VOICE_QUALITY_THRESHOLD = _env_float("VOICE_QUALITY_THRESHOLD", 0.55)
VOICE_ACTIVITY_THRESHOLD = _env_float("VOICE_ACTIVITY_THRESHOLD", 0.35)
VOICE_SIMILARITY_THRESHOLD = _env_float("VOICE_SIMILARITY_THRESHOLD", 0.75)

IRIS_QUALITY_THRESHOLD = _env_float("IRIS_QUALITY_THRESHOLD", 0.55)
IRIS_SIMILARITY_THRESHOLD = _env_float("IRIS_SIMILARITY_THRESHOLD", 0.78)

FUSION_VOICE_WEIGHT = _env_float("FUSION_VOICE_WEIGHT", 0.50)
FUSION_IRIS_WEIGHT = _env_float("FUSION_IRIS_WEIGHT", 0.50)
FUSION_THRESHOLD = _env_float("FUSION_THRESHOLD", 0.80)

DEVELOPMENT_THRESHOLDS = _env_bool("DEVELOPMENT_THRESHOLDS", True)
RETAIN_PROCESSED_UPLOADS = _env_bool("RETAIN_PROCESSED_UPLOADS", False)




