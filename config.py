"""Smart Parcel Box – application configuration."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FAISS_DIR = DATA_DIR / "faiss_index"
DB_PATH = DATA_DIR / "parcel_box.db"
STATIC_DIR = BASE_DIR / "static"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
FAISS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"
APP_HOST = os.getenv("SPB_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("SPB_PORT", "8080"))

# AI Face Model
# On Raspberry Pi 4, set to "buffalo_s" for 10-15 FPS. On PC/Pi5 with good CPU, "buffalo_l" is supported.
FACE_MODEL_NAME = os.getenv("FACE_MODEL_NAME", "buffalo_s")
FACE_DET_SIZE = int(os.getenv("FACE_DET_SIZE", "320"))
ONNX_PROVIDER = os.getenv("ONNX_PROVIDER", "cpu")  # "cpu" or "cuda"

# Anti-spoofing
ANTI_SPOOFING_MODEL_PATH = Path(
    os.getenv(
        "ANTI_SPOOFING_MODEL_PATH",
        str(DATA_DIR / "models" / "anti_spoofing" / "AntiSpoofing_bin_1.5_128.onnx"),
    )
)
ANTI_SPOOFING_THRESHOLD = float(os.getenv("ANTI_SPOOFING_THRESHOLD", "0.5"))
ANTI_SPOOFING_CROP_SCALE = float(os.getenv("ANTI_SPOOFING_CROP_SCALE", "1.5"))
ANTI_SPOOFING_PROVIDER = os.getenv("ANTI_SPOOFING_PROVIDER", "cpu")

# Recognition Thresholds
RECOGNITION_THRESHOLD = 0.45
MAX_FAILED_ATTEMPTS = 5
REGISTRATION_FRAMES_REQUIRED = 5
MIN_FACE_QUALITY = 0.35
DUPLICATE_THRESHOLD = 0.55  # Cosine similarity >= 0.55 -> duplicate

# Edge Camera & Streaming (Decoupled Architecture like FTA)
CAMERA_SOURCE = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
STREAM_FPS = int(os.getenv("CAMERA_FPS", "25"))
STREAM_PREVIEW_FPS = int(os.getenv("STREAM_PREVIEW_FPS", "15"))
RECOGNITION_INTERVAL_FRAMES = int(os.getenv("RECOGNITION_INTERVAL_FRAMES", "5"))
RECOGNITION_MAX_STALE_MS = int(os.getenv("RECOGNITION_MAX_STALE_MS", "1000"))

# Security (Fernet Encryption Key)
FERNET_KEY_FILE = DATA_DIR / "fernet.key"

# Locker Count
TOTAL_LOCKERS = 6
