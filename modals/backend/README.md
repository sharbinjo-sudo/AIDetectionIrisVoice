# BioFusion AI Backend

This Django backend exposes the privacy-first API expected by the Flutter frontend in `frontend/`.

## What it includes

- `GET /api/v1/health/`
- `POST /api/v1/test/iris/`
- `POST /api/v1/test/voice/`
- `POST /api/v1/biometric-authenticate/`

The live verification flow uses temporary uploads only and does not save biometric media or successful verification attempts. It uses:

- local `SpeechBrain ECAPA` files from `backend/pretrained_models/voice` for speaker embeddings
- local `iris_semseg_upp_scse_mobilenetv2.onnx` from `backend/pretrained_models/iris` for iris segmentation and blink analysis

## Important runtime note

The current machine is using Python `3.14.5`. If any ML package install fails, create a Python `3.11` or `3.12` virtual environment for the backend and install the requirements there. Django itself will run on newer Python versions, but some heavy ML dependencies may lag behind.

## Install

```powershell
cd C:\Users\sharb\Videos\Iris_Voice\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Warm the pretrained models

The backend now prefers the copied local models in `backend/pretrained_models`. The warm-up command should report `mode=local_pretrained` for voice and `mode=local_onnx` for iris.

Run:

```powershell
python manage.py warm_biometric_models
```

If a heavy dependency is unavailable locally, the backend falls back to built-in heuristic voice and blink checks so the app can still run end to end during development.

## Migrate

```powershell
python manage.py migrate
```

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

## Privacy mode and pretrained model behavior

- The speaker engine first tries `LOCAL_VOICE_MODEL_DIR`, then falls back to `VOICE_MODEL_SOURCE` if the local folder is incomplete.
- The iris engine first tries `LOCAL_IRIS_ONNX_MODEL_PATH`, then falls back to MediaPipe, then to the built-in heuristic analyzer for local demos.
- The live IRL flow performs temporary blink-plus-speech human verification only. It does not save biometric uploads or completed verification results.
- Verification persistence is disabled by design, so the app does not store biometric media or save completed checks.

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

- Open `IRL`
- Tick `I am not a robot`
- Keep one eye in frame
- Capture the open-eye step
- Blink when prompted
- Speak the phrase clearly into the mic
- Wait for the final `Verified as Human` or `Verification Failed` screen
