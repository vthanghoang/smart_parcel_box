"""Camera Service for Smart Parcel Box (Edge Device USB/V4L2/DShow Capture).
Directly captures frames on edge hardware in a dedicated thread-safe background thread.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Optional

import cv2
import numpy as np

import config as cfg

logger = logging.getLogger(__name__)


class CameraService:
    """Manages camera capture on Edge hardware (RPi 4/5 or PC USB/CSI camera).
    Runs a dedicated background capture loop with CAP_PROP_BUFFERSIZE=1 to minimize latency.
    """

    def __init__(
        self,
        source: int | str = cfg.CAMERA_SOURCE,
        width: int = cfg.CAMERA_WIDTH,
        height: int = cfg.CAMERA_HEIGHT,
        fps: int = cfg.STREAM_FPS,
    ):
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._starting = False
        self._frame_count = 0
        self._last_frame_time = 0.0

    def start(self):
        """Start background camera capture loop without blocking main thread."""
        if self._running:
            return
        self._running = True
        self._starting = True
        self._thread = threading.Thread(target=self._capture_loop, name="EdgeCameraThread", daemon=True)
        self._thread.start()
        logger.info("CameraService starting on source: %s", self.source)

    def stop(self):
        """Stop background capture loop and release device."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None
        self._disconnect()
        self._starting = False
        logger.info("CameraService stopped")

    def get_frame(self) -> Optional[np.ndarray]:
        """Thread-safe retrieval of the most recent edge camera frame."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def _connect(self):
        """Open edge camera with OS-specific backend optimizations."""
        try:
            if isinstance(self.source, int) and sys.platform.startswith("win"):
                # Windows DirectShow for faster initialization & hardware acc
                self._cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            elif isinstance(self.source, int) and sys.platform.startswith("linux"):
                # Linux / Raspberry Pi V4L2 backend
                self._cap = cv2.VideoCapture(self.source, cv2.CAP_V4L2)
            else:
                self._cap = cv2.VideoCapture(self.source)

            if isinstance(self.source, int) and self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._cap.set(cv2.CAP_PROP_FPS, self.fps)
                # Set minimal buffer size to avoid stale lag
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._connected = self._cap.isOpened()
            self._starting = False
            if self._connected:
                logger.info("Edge camera connected successfully: %s (%dx%d @ %d FPS)",
                            self.source, self.width, self.height, self.fps)
            else:
                logger.warning("Edge camera source not available: %s", self.source)
        except Exception as e:
            logger.error("Error opening edge camera: %s", e)
            self._connected = False
            self._starting = False

    def _disconnect(self):
        """Release video capture device."""
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self._connected = False
        with self._lock:
            self._frame = None

    def _capture_loop(self):
        """Continuous non-blocking frame grabber loop running on edge device."""
        reconnect_delay = 2.0
        frame_interval = 1.0 / max(1, self.fps)

        while self._running:
            if not self._connected or not self._cap or not self._cap.isOpened():
                self._starting = True
                self._connect()
                if not self._connected:
                    time.sleep(reconnect_delay)
                    continue

            try:
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self._frame = frame
                    self._last_frame_time = time.time()
                    self._frame_count += 1
                else:
                    self._connected = False
                    logger.warning("Failed to grab frame from edge camera, reconnecting...")
            except Exception as e:
                logger.error("Camera capture exception: %s", e)
                self._connected = False

            time.sleep(frame_interval)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        return {
            "source": str(self.source),
            "connected": self._connected,
            "running": self._running,
            "starting": self._starting,
            "fps": self.fps,
            "frame_count": self._frame_count,
        }


# Singleton edge camera service
camera_service = CameraService()
