# Offline web app

Internet is not required when the local web server and Django backend are
running. Install dependencies and all local deployed model files before disconnecting.

Build once from `frontend` (rebuild after code changes):

```powershell
flutter build web --release --no-pub --no-web-resources-cdn
```

Start the backend from `backend`, with its Python environment active:

```powershell
$env:BIOMETRIC_OFFLINE_MODE = 'true'
python manage.py runserver 127.0.0.1:8000 --noreload
```

In a second terminal, from `frontend`:

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory build/web
```

Open **http://localhost:8080** and keep both servers running. Set the API URL
to `http://127.0.0.1:8000/api/v1`. Do not open HTML using `file://`.
These servers are for local testing, not public production hosting.

CanvasKit and standard Roboto fonts load locally. Additional language scripts
need their own bundled fonts. Restart `flutter run` after HTML/bootstrap changes;
hot reload cannot update the loader. Prefer the release build for presentations.

Test by disconnecting Wi-Fi and opening a fresh private browser window while
both servers run. Check capture, enrollment and login. Do not use DevTools'
global Offline switch: it blocks localhost/API requests too. Stopping Django
must prevent authentication, but should not blank the UI. This is local,
internet-independent operation, not a serverless cached PWA. Biometric API
responses are not cached. A startup retry screen handles loading failures.

## Flutter resources

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.
