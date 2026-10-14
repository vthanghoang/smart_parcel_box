"""Face detection, recognition, registration and FAISS index management."""

from __future__ import annotations

import logging
import os
import site
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import faiss
import numpy as np

import config as cfg

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512

# ---------------------------------------------------------------------------
# CUDA DLL helpers (same approach as FTA)
# ---------------------------------------------------------------------------
_dll_handles: list = []

def _prepare_cuda_path():
    sp = Path(site.getsitepackages()[0])
    dirs = [sp / "nvidia" / sub / "bin" for sub in ("cublas", "cudnn", "cuda_nvrtc")]
    existing = [str(d) for d in dirs if d.exists()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing + [os.environ.get("PATH", "")])


# ---------------------------------------------------------------------------
# InsightFace wrapper
# ---------------------------------------------------------------------------
class FaceEngine:
    """Thin wrapper around InsightFace + FAISS index."""

    def __init__(self):
        self._app = None
        self._index: Optional[faiss.IndexFlatIP] = None
        self._id_map: List[int] = []  # faiss row → user.id
        self._initialized = False

    # -- lifecycle -----------------------------------------------------------

    def initialize(self):
        if self._initialized:
            return
        t0 = time.time()
        _prepare_cuda_path()

        import onnxruntime as ort
        avail = ort.get_available_providers()
        req = cfg.ONNX_PROVIDER.strip().lower()
        if req in ("cuda", "gpu") and "CUDAExecutionProvider" in avail:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            ctx = 0
        else:
            providers = ["CPUExecutionProvider"]
            ctx = -1

        from insightface.app import FaceAnalysis
        self._app = FaceAnalysis(name=cfg.FACE_MODEL_NAME, providers=providers)
        self._app.prepare(ctx_id=ctx, det_size=(cfg.FACE_DET_SIZE, cfg.FACE_DET_SIZE))
        self._load_or_create_index()
        self._initialized = True
        logger.info("FaceEngine ready in %.2fs  index=%d vectors", time.time() - t0, self.total_faces)

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def _load_or_create_index(self):
        idx_path = cfg.FAISS_DIR / "parcel_index.bin"
        map_path = cfg.FAISS_DIR / "parcel_map.npy"
        if idx_path.exists() and map_path.exists():
            self._index = faiss.read_index(str(idx_path))
            self._id_map = list(np.load(str(map_path), allow_pickle=True))
        else:
            self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self._id_map = []

    def save_index(self):
        faiss.write_index(self._index, str(cfg.FAISS_DIR / "parcel_index.bin"))
        np.save(str(cfg.FAISS_DIR / "parcel_map.npy"), np.array(self._id_map, dtype=object))

    # -- detection / recognition ---------------------------------------------

    def detect(self, frame: np.ndarray, min_score: float = 0.5):
        """Return list of dicts with bbox, embedding, det_score, quality."""
        faces = self._app.get(frame)
        results = []
        for f in faces:
            if float(f.det_score) < min_score:
                continue
            results.append({
                "bbox": f.bbox.astype(int).tolist(),
                "embedding": f.normed_embedding.astype(np.float32),
                "det_score": float(f.det_score),
                "quality": self._quality(f, frame),
            })
        return results

    def recognize(self, embedding: np.ndarray) -> Tuple[Optional[int], float]:
        """Search FAISS. Returns (user_id, similarity) or (None, 0)."""
        if self._index is None or self._index.ntotal == 0:
            return None, 0.0
        q = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(q)
        D, I = self._index.search(q, 1)
        idx, sim = int(I[0][0]), float(D[0][0])
        if idx == -1 or sim < cfg.RECOGNITION_THRESHOLD:
            return None, sim
        return self._id_map[idx], sim

    def check_duplicate(self, embedding: np.ndarray) -> Optional[int]:
        """Return user_id if embedding too close to existing face."""
        if self._index is None or self._index.ntotal == 0:
            return None
        q = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(q)
        D, I = self._index.search(q, 1)
        idx, sim = int(I[0][0]), float(D[0][0])
        if idx != -1 and sim >= cfg.DUPLICATE_THRESHOLD:
            return self._id_map[idx]
        return None

    def add_face(self, user_id: int, embedding: np.ndarray):
        vec = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        self._index.add(vec)
        self._id_map.append(user_id)
        self.save_index()

    # -- quality assessment --------------------------------------------------

    @staticmethod
    def _quality(face, frame: np.ndarray) -> float:
        det = float(face.det_score) * 0.3
        bbox = face.bbox
        fw, fh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        H, W = frame.shape[:2]
        ratio = (fw * fh) / (W * H)
        size = (1.0 if 0.05 <= ratio <= 0.30 else 0.6 if ratio >= 0.01 else 0.2) * 0.25
        aspect = fw / max(fh, 1)
        asp = (1.0 if 0.65 <= aspect <= 0.85 else 0.7 if 0.5 <= aspect <= 1.0 else 0.3) * 0.15
        x1, y1, x2, y2 = max(0, int(bbox[0])), max(0, int(bbox[1])), min(W, int(bbox[2])), min(H, int(bbox[3]))
        blur = 0.0
        if x2 > x1 and y2 > y1:
            gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            lv = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur = (1.0 if lv > 200 else 0.8 if lv > 100 else 0.5 if lv > 50 else 0.2) * 0.3
        return min(det + size + asp + blur, 1.0)

    @property
    def total_faces(self) -> int:
        return self._index.ntotal if self._index else 0


# Singleton
face_engine = FaceEngine()
