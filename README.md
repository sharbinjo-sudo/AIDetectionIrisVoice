# Advanced Human Recognition

An offline-first, local multibiometric authentication prototype for account
registration and login. The example uses a customer ID and PIN flow; the
architecture is not limited to banking.

## What it does

Registration captures multiple camera samples and voice recordings, validates
quality, and stores protected biometric templates. Login captures fresh camera
and voice samples, compares them with the enrolled templates, and reports
individual quality, similarity, fusion, and rejection reasons. Liveness and
identity verification are reported separately; identity matching is not proof
that a subject is human.

The camera step is presented as an iris/camera capture in the UI, but the
configured low-quality-camera prototype can use the full camera frame for face
template matching while retaining iris captures for the configured iris path.
The backend health screen deliberately says **Local deployed model** rather than
claiming that this project trained the upstream model weights.

## Technology stack

### Frontend

- Flutter/Dart 3.11+
- Flutter Web release build with locally bundled CanvasKit and Roboto fonts
- Material 3 UI
- Riverpod state management
- GoRouter navigation
- Dio HTTP client and multipart capture uploads
- `camera` for live camera preview/capture
- `record` and `audioplayers` for voice capture/playback
- `flutter_secure_storage` for session token and customer ID storage
- MediaPipe Face Landmarker for eye-ROI localization where enabled

### Backend

- Python 3.11–3.14 compatible Django 5.2 and Django REST Framework
- SQLite for local development (replace with PostgreSQL for deployment)
- OpenCV and NumPy for image processing
- InsightFace buffalo_l SCRFD/ArcFace ONNX assets for face detection/embeddings
- SpeechBrain ECAPA-TDNN local assets for speaker embeddings
- Worldcoin iris semantic-segmentation ONNX asset for iris segmentation
- MediaPipe Face Landmarker asset for eye localization only
- Quality-aware multimodal fusion with diagnostic reason codes
- Django signed sessions, hashed PINs, throttled login attempts, and encrypted
  biometric templates

## Repository layout

```text
frontend/                 Flutter application and web assets
backend/                  Django API, models, services, migrations and tests
backend/biometrics/       Authentication, capture and fusion implementation
docs/                     Reason codes and technical notes
registration_exports/     Local CSV registration audit (ignored by Git)
```

## Local setup

```powershell
cd backend
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py warm_biometric_models
python manage.py runserver 127.0.0.1:8000 --noreload
```

In another terminal:

```powershell
cd frontend
flutter pub get
flutter run -d chrome --web-port 8080
```

For an offline presentation, provision all local model assets first and build:

```powershell
flutter build web --release --no-pub --no-web-resources-cdn
python -m http.server 8080 --bind 127.0.0.1 --directory build/web
```

Keep Django and the local web server running. Internet is not needed, but the
browser still needs the local API for biometric decisions. See
`frontend/README.md` and `backend/README.md` for offline details.

## Validation

```powershell
cd backend
python manage.py test biometrics
cd ../frontend
flutter test
```

Model assets are stored under `backend/trained_models/` for local execution.
Do not commit model weights, database files, media, generated builds, session
secrets, or `registration_exports/registrations.csv`. Review upstream model
licenses before commercial deployment.
