# Smart Parcel Box Edge Runtime

Run the FastAPI application on the Raspberry Pi connected to the camera. In this
setup, "server" means the local application process on the Pi: camera capture,
face detection, recognition, and FAISS lookup all stay on the edge device. The
browser sends control messages and displays the Pi's preview; it does not open
or upload frames from a client camera.

## Camera and recognition flow

- `CameraService` captures frames continuously on the Pi.
- The WebSocket sends the latest annotated preview at `STREAM_PREVIEW_FPS`
  (default 15 FPS).
- Face recognition runs in a single background worker every
  `RECOGNITION_INTERVAL_FRAMES` (default 5 captured frames), without blocking
  preview delivery.
- Results from an earlier recognition or registration mode are discarded.
  Recent face annotations are reused between AI runs and removed after
  `RECOGNITION_MAX_STALE_MS` (default 1000 ms).

The default `buffalo_s` model is selected for Raspberry Pi 4 CPU inference.
Tune `FACE_MODEL_NAME`, `CAMERA_FPS`, `STREAM_PREVIEW_FPS`,
`RECOGNITION_INTERVAL_FRAMES`, and `RECOGNITION_MAX_STALE_MS` with environment
variables for the installed camera and target latency.

## Fullscreen Raspberry Pi kiosk

The FastAPI app continues to serve the local UI, but the operator does not need
to open a browser or enter a URL. From a Raspberry Pi OS desktop session, run:

```bash
chmod +x start_kiosk.sh
./start_kiosk.sh
```

The launcher starts the camera and AI backend on `127.0.0.1:8080`, waits for
`/api/health`, then opens the kiosk window fullscreen without browser controls.
Press `Alt+F4` to close it; the launcher stops the backend as well. Backend
startup output is written to `data/kiosk-backend.log`. The default backend
binding is still `0.0.0.0:8080` when running `python main.py` directly; override
it with `SPB_HOST` and `SPB_PORT` when needed.

Install Chromium and the project's Python dependencies in a Raspberry Pi
virtual environment before launching. For testing from a terminal, activate
that environment first; the launcher uses `../.venv/bin/python` by default or
the interpreter specified by `SPB_PYTHON`.

To open the kiosk automatically after desktop login, add
`./start_kiosk.sh` (using its absolute path) to the desktop session's
Autostart Applications. The Pi should log in to the kiosk desktop user
automatically; do not run Chromium as root.

## Anti-spoofing

The bundled ONNX anti-spoofing model runs locally through ONNX Runtime and
defaults to the CPU provider. It checks every detected face in each AI worker
run; frames that fail the live-class threshold are not used for authentication
or face registration. The model must initialize successfully at startup;
missing or invalid model files stop startup rather than silently disabling the
check.

Configure `ANTI_SPOOFING_MODEL_PATH`, `ANTI_SPOOFING_THRESHOLD` (default `0.5`),
`ANTI_SPOOFING_CROP_SCALE` (default `1.5`), and `ANTI_SPOOFING_PROVIDER`
(`cpu`, or `cuda` when supported). Check `/api/health` to confirm the model is
loaded and see the active ONNX provider.

This model-based presentation-attack check is not a guarantee against every
spoofing technique. Validate its performance with the actual camera, lighting,
and expected attack types before relying on it for unattended access.
