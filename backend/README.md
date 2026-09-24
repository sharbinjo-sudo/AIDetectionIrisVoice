# BioFusion AI Backend

This Django backend exposes the privacy-first API expected by the Flutter frontend in `frontend/`.

## What it includes

- `GET /api/v1/health/`
- `POST /api/v1/test/iris/`
- `POST /api/v1/test/voice/`
- `POST /api/v1/banking/register/`
- `POST /api/v1/banking/login/`
- `POST /api/v1/users/<user_id>/enrollment/`
- `POST /api/v1/biometric-authenticate/`

Registration accepts `full_name`, `mobile_number`, and a four-digit `pin`.
The backend generates a unique six-digit customer ID. Login accepts
`customer_id` and `pin`, followed by biometric verification. PINs are hashed;
passwords and account numbers are no longer stored. Migration 0009 converts
legacy alphanumeric customer IDs to numeric IDs without changing PINs or
biometric templates. PIN login attempts are rate-limited per customer and IP address.

Registration records encrypted, aggregated face, iris, and voice templates after all captures pass quality checks. Login returns a short-lived signed session, then fresh temporal samples are compared with those enrolled templates. Raw biometric media is temporary and deleted after processing; diagnostic scores and decisions may be stored for local auditing. It uses:

- local InsightFace `buffalo_l` SCRFD detection and ArcFace recognition ONNX files
- local `SpeechBrain ECAPA` files from `backend/trained_models/voice` for speaker embeddings
- local `iris_semseg_upp_scse_mobilenetv2.onnx` from `backend/trained_models/iris` for iris segmentation

## Important runtime note

The current machine is using Python `3.14.5`. If any ML package install fails, create a Python `3.11` or `3.12` virtual environment for the backend and install the requirements there. Django itself will run on newer Python versions, but some heavy ML dependencies may lag behind.

## Install

```powershell
cd C:\Users\sharb\Videos\Iris_Voice\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Warm the local deployed models

The backend prefers copied local model assets in `backend/trained_models`. The warm-up command checks local readiness for face, voice, and iris.

Provision the two buffalo_l files at these exact paths:

```text
backend/trained_models/face/models/buffalo_l/det_10g.onnx
backend/trained_models/face/models/buffalo_l/w600k_r50.onnx
```

The files in this workspace were obtained from `immich-app/buffalo_l` and
verified with SHA-256 `5838f7fe...b85b5b91` (detector) and
`4c06341c...fc619e43` (recognition). Review the linked InsightFace model
license before commercial deployment.

Runtime is offline-first by default (`BIOMETRIC_OFFLINE_MODE=true`). The app
does not download models while authenticating. The local Worldcoin ONNX model,
SpeechBrain files, buffalo_l files, and cached `backend/.model_cache/iris/face_landmarker.task`
must be present before disconnecting from the internet. The Flutter UI uses
platform fonts and does not fetch Google Fonts at runtime. A local Django
process is still required because the Flutter client calls it over loopback.

Run:

```powershell
python manage.py warm_biometric_models
```

Development mode may use a heuristic voice-quality fallback when SpeechBrain
cannot load. Iris enrollment and authentication never fall back to fixed or
heuristic detection: the Worldcoin ONNX segmenter and the MediaPipe eye-ROI
asset must both be ready.

With development `DEBUG=True`, the low-quality-camera submission prototype
defaults to face+voice identity matching while the camera step remains labelled
Iris in the frontend. The uploaded full frames build a real face template; iris
is not identity evidence in this mode. Tests and production default to strict
mode. Production must use `DEBUG=False`; startup rejects an explicitly enabled
face-primary prototype, and strict face+iris+voice matching is used.

Registration collects three camera frames and three quality-checked voice
recordings, then aggregates the face and speaker embeddings into protected
templates. Login is deliberately separate: it accepts one live camera frame
and one voice recording, quality-gates them, and compares them with those
enrollment templates.

## Migrate

```powershell
python manage.py migrate
```

## Calibrate the authentication operating point

The configured `FUSION_THRESHOLD` is development-only. For production, collect
representative genuine-user and impostor sessions containing the separate
face, iris, and voice similarity/quality measurements, then run:

```powershell
python manage.py calibrate_fusion_thresholds --genuine genuine.json --impostor impostor.json --max-fpr 0.02
```

Set `DEVELOPMENT_THRESHOLDS=False` in production. Authentication then fails
closed unless a valid `FUSION_CALIBRATION_PATH` exists; the application never
pretends an arbitrary percentage is calibrated.

## Run the server

```powershell
python manage.py runserver 0.0.0.0:8000
```

## Frontend connection

The Flutter app defaults to:

```text
Windows/Chrome: http://127.0.0.1:8000/api/v1
Android emulator: http://10.0.2.2:8000/api/v1
```

For a real Android device, change the frontend base URL to:

```text
http://YOUR_COMPUTER_LAN_IP:8000/api/v1
```

You can set that address at build time so a release does not start with the
emulator-only address:

```powershell
flutter run -d YOUR_DEVICE_ID --dart-define=API_BASE_URL=http://192.168.1.20:8000/api/v1
```

For local web development, `flutter run -d chrome` can use the default
`http://127.0.0.1:8000/api/v1` address. Camera, microphone, and protected
browser storage require either `localhost` or a secure HTTPS page. For a
deployed web build, compile the public HTTPS API address into the app:

```powershell
flutter build web --release --dart-define=API_BASE_URL=https://api.example.com/api/v1
```

When `DEBUG=false`, allow the exact frontend origin in the backend environment
(an origin has no path):

```text
CORS_ALLOWED_ORIGINS=https://app.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com
```

Serve both the web app and API over HTTPS. An HTTPS web page cannot call an
HTTP API because browsers block mixed content. Camera and microphone access
must also be allowed in the browser's site controls.

The phone and backend computer must be on the same network and the operating
system firewall must allow TCP port 8000. For a deployed production build,
use an HTTPS API address instead of a private HTTP address.

## Android release signing

Copy `frontend/android/key.properties.example` to
`frontend/android/key.properties`, point it at the private upload keystore,
and keep the keystore and populated properties file outside source control.
Gradle uses the production key automatically when that file exists; without
it, the release APK is debug-signed and is suitable only for local testing.

## Privacy mode and local model behavior

- The speaker engine first tries `LOCAL_VOICE_MODEL_DIR`, then falls back to `VOICE_MODEL_SOURCE` if the local folder is incomplete.
- MediaPipe Face Landmarker localizes the eye ROI; it is not used as a face-recognition or iris-recognition model.
- The Worldcoin ONNX segmenter validates and isolates the iris before its deterministic texture pattern is stored or compared.
- The SpeechBrain ECAPA model creates and compares speaker embeddings.
- Registration stores Fernet-encrypted, aggregated templates, not uploaded camera/audio files. Set an independent `BIOMETRIC_TEMPLATE_KEYS` value in production and retain old keys during key rotation.
- Login capture quality failures request a retry; a usable template mismatch is reported separately.
- Face and iris verification aggregate at least three frames. Voice verification aggregates at least two non-overlapping ECAPA segments.
- Identity matching is not described as liveness. The response reports dedicated anti-spoofing as `NOT_EVALUATED` until such a model is explicitly added.

## Local run order

1. Start the backend:

```powershell
cd C:\Users\sharb\Videos\Iris_Voice\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py warm_biometric_models
python manage.py runserver 0.0.0.0:8000
```

2. Start the Flutter frontend in a second terminal:

```powershell
cd C:\Users\sharb\Videos\Iris_Voice\frontend
flutter pub get
flutter run -d chrome
```

3. In the app:

- Register a banking profile, then complete face, iris, and voice enrollment.
- Return to Home and log in with the registered credentials.
- In the combined face + iris camera step, keep exactly one face visible and
  capture three segmentation-validated eye frames. The same accepted full
  frames are passed invisibly to the face matcher; no second camera step is
  shown.
- Record the full voice phrase clearly in a quiet place.
- Review the template similarity, capture quality, and final biometric decision.
