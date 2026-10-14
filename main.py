"""Smart Parcel Box – FastAPI backend with Edge Camera Service,
Decoupled Asynchronous AI Pipeline (FTA Architecture), Fernet Encryption,
and Hardware Locker Management.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import config as cfg
from database import (
    init_db, SessionLocal, User, Locker, Transaction, AuditLog,
)
from services.camera_service import camera_service
from services.crypto import encrypt_embedding, decrypt_embedding
from services.anti_spoofing import AntiSpoofingService
from services.face_engine import face_engine
from services.locker_manager import locker_mgr

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

# Keep the preview responsive and serialize inference against the shared face engine.
ai_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="EdgeAIWorker")
anti_spoofing = AntiSpoofingService(
    model_path=cfg.ANTI_SPOOFING_MODEL_PATH,
    threshold=cfg.ANTI_SPOOFING_THRESHOLD,
    onnx_provider=cfg.ANTI_SPOOFING_PROVIDER,
    crop_scale=cfg.ANTI_SPOOFING_CROP_SCALE,
)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_initial_lockers()
    anti_spoofing.initialize()
    face_engine.initialize()
    camera_service.start()
    logger.info(
        "Smart Parcel Box edge services ready (face=%s, anti-spoof=%s)",
        cfg.FACE_MODEL_NAME,
        anti_spoofing.active_provider,
    )
    try:
        yield
    finally:
        camera_service.stop()
        ai_executor.shutdown(wait=True, cancel_futures=True)


app = FastAPI(title="Smart Parcel Box System", lifespan=lifespan)
cfg.STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(cfg.STATIC_DIR)), name="static")


def _seed_initial_lockers():
    db = SessionLocal()
    try:
        existing = db.query(Locker).count()
        if existing == 0:
            for i in range(1, cfg.TOTAL_LOCKERS + 1):
                db.add(Locker(number=f"L{i:02d}", status="available"))
            db.commit()
            logger.info("Seeded %d default lockers", cfg.TOTAL_LOCKERS)
    finally:
        db.close()


def _audit(db, user_id=None, role=None, receiver_id=None, locker_id=None,
           auth_result=None, parcel_status=None, action=None):
    """Centralized audit logger ensuring all security events are persistently recorded."""
    try:
        log = AuditLog(
            user_id=user_id,
            role=role,
            receiver_id=receiver_id,
            locker_id=locker_id,
            auth_result=auth_result,
            parcel_status=parcel_status,
            action=action,
            timestamp=dt.datetime.utcnow(),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error("Audit log failure: %s", e)
        db.rollback()


# ---------------------------------------------------------------------------
# Static Pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = cfg.STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Smart Parcel Box UI loading...</h1>", status_code=200)
    return FileResponse(index_file)


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "face_model_loaded": face_engine.is_initialized,
        "face_model_name": cfg.FACE_MODEL_NAME,
        "anti_spoofing_enabled": True,
        "anti_spoofing_model_loaded": anti_spoofing.is_initialized,
        "anti_spoofing_provider": anti_spoofing.active_provider,
        "anti_spoofing_last_error": anti_spoofing.last_error,
        "camera": camera_service.get_status(),
    }


# ---------------------------------------------------------------------------
# User & Receiver REST Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/receivers")
async def list_receivers():
    """List receivers showing ONLY receiver name and masked last 3 digits of phone number."""
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.role == "receiver", User.is_active == True).all()
        return [
            {
                "id": u.id,
                "name": u.name,
                "phone_masked": u.phone_masked,
                "management_unit": u.management_unit or "",
                "external_id": u.external_id or "",
            }
            for u in users
        ]
    finally:
        db.close()


@app.get("/api/user/{user_id}")
async def get_user_details(user_id: int):
    db = SessionLocal()
    try:
        u = db.query(User).get(user_id)
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": u.id,
            "name": u.name,
            "role": u.role,
            "phone_masked": u.phone_masked,
            "management_unit": u.management_unit,
            "external_id": u.external_id,
        }
    finally:
        db.close()


@app.post("/api/register")
async def register_user(data: dict):
    """Save user details after face embedding is captured and checked via WebSocket.
    Stores encrypted face embedding at rest via Fernet.
    """
    db = SessionLocal()
    try:
        embedding_hex = data.get("embedding_hex")
        if not embedding_hex:
            raise HTTPException(status_code=400, detail="Missing face embedding data")

        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        role = data.get("role", "receiver").strip().lower()
        management_unit = data.get("management_unit", "").strip()
        external_id = data.get("external_id", "").strip()

        if not name or not phone:
            raise HTTPException(status_code=400, detail="Name and phone are required")

        raw_bytes = bytes.fromhex(embedding_hex)
        enc_bytes = encrypt_embedding(raw_bytes)

        user = User(
            name=name,
            phone=phone,
            role=role,
            management_unit=management_unit,
            external_id=external_id,
            face_embedding_enc=enc_bytes,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Update FAISS index
        embedding = np.frombuffer(raw_bytes, dtype=np.float32)
        face_engine.add_face(user.id, embedding)

        _audit(
            db,
            user_id=user.id,
            role=role,
            auth_result="registered",
            action=f"Registered new {role}: {name}",
        )

        return {
            "ok": True,
            "user_id": user.id,
            "name": user.name,
            "role": user.role,
            "phone_masked": user.phone_masked,
            "message": "User registered successfully",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Shipper Flow: Deposit Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/deposit/check_locker")
async def check_deposit_locker(data: dict):
    """Check if locker assigned to receiver or general available locker exists."""
    db = SessionLocal()
    try:
        receiver_id = data.get("receiver_id")
        if not receiver_id:
            raise HTTPException(status_code=400, detail="receiver_id required")

        # Preferred: locker previously assigned to receiver and currently available
        locker = db.query(Locker).filter(
            Locker.assigned_receiver_id == receiver_id,
            Locker.status == "available",
        ).first()

        if not locker:
            # Fallback: any available locker
            locker = db.query(Locker).filter(Locker.status == "available").first()

        if not locker:
            return {"available": False, "message": "All lockers are currently occupied"}

        return {
            "available": True,
            "locker_number": locker.number,
            "locker_id": locker.id,
        }
    finally:
        db.close()


@app.post("/api/deposit/open")
async def open_deposit_locker(data: dict):
    """Open locker for shipper to deposit parcel."""
    db = SessionLocal()
    try:
        shipper_id = data.get("shipper_id")
        receiver_id = data.get("receiver_id")
        locker_id = data.get("locker_id")

        if not shipper_id or not receiver_id or not locker_id:
            raise HTTPException(status_code=400, detail="Missing required parameters")

        locker = db.query(Locker).get(locker_id)
        if not locker or locker.status != "available":
            raise HTTPException(status_code=400, detail="Locker not available")

        # Reserve locker
        locker.status = "occupied"
        locker.assigned_receiver_id = receiver_id

        # Create active transaction in pending/deposited state
        tx = Transaction(
            shipper_id=shipper_id,
            receiver_id=receiver_id,
            locker_id=locker.id,
            status="deposited",
            deposited_at=dt.datetime.utcnow(),
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)

        # Trigger hardware relay to open locker
        locker_mgr.open_locker(locker.number)

        _audit(
            db,
            user_id=shipper_id,
            role="shipper",
            receiver_id=receiver_id,
            locker_id=locker.id,
            parcel_status="deposit_opened",
            action="Locker opened for parcel deposit",
        )

        return {
            "ok": True,
            "locker_number": locker.number,
            "transaction_id": tx.id,
            "status": "opened",
        }
    finally:
        db.close()


@app.post("/api/deposit/sensor_detect")
async def deposit_sensor_detect(data: dict):
    """Detect parcel placement inside locker using simulated or GPIO sensor."""
    locker_number = data.get("locker_number")
    locker_mgr.simulate_parcel_placed(locker_number)
    detected = locker_mgr.detect_parcel(locker_number)
    return {"ok": True, "parcel_detected": detected}


@app.post("/api/deposit/complete")
async def complete_deposit(data: dict):
    """Close and lock locker, finalize transaction as Deposited."""
    db = SessionLocal()
    try:
        tx_id = data.get("transaction_id")
        locker_number = data.get("locker_number")

        tx = db.query(Transaction).get(tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Hardware: close and lock locker
        locker_mgr.close_locker(locker_number)

        tx.status = "deposited"
        db.commit()

        _audit(
            db,
            user_id=tx.shipper_id,
            role="shipper",
            receiver_id=tx.receiver_id,
            locker_id=tx.locker_id,
            auth_result="success",
            parcel_status="deposited",
            action=f"Parcel successfully deposited into Locker {locker_number}",
        )

        return {
            "ok": True,
            "status": "deposited",
            "locker_number": locker_number,
            "transaction_id": tx.id,
            "deposited_at": tx.deposited_at.strftime("%Y-%m-%d %H:%M:%S") if tx.deposited_at else "",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Receiver Flow: Collection Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/receiver/{receiver_id}/active_parcel")
async def get_receiver_active_parcel(receiver_id: int):
    """Find active parcel for receiver. ONLY opens if parcel status is Deposited."""
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(
            Transaction.receiver_id == receiver_id,
            Transaction.status == "deposited",
        ).first()

        if not tx:
            return {
                "has_parcel": False,
                "message": "No active parcel found awaiting pickup for your account.",
            }

        locker = db.query(Locker).get(tx.locker_id)
        return {
            "has_parcel": True,
            "transaction_id": tx.id,
            "locker_id": locker.id,
            "locker_number": locker.number,
            "deposited_at": tx.deposited_at.strftime("%Y-%m-%d %H:%M:%S") if tx.deposited_at else "",
            "shipper_name": tx.shipper.name if tx.shipper else "Shipper",
        }
    finally:
        db.close()


@app.post("/api/collect/open")
async def open_collect_locker(data: dict):
    """Open locker for receiver after verifying active parcel."""
    db = SessionLocal()
    try:
        receiver_id = data.get("receiver_id")
        tx_id = data.get("transaction_id")

        tx = db.query(Transaction).filter(
            Transaction.id == tx_id,
            Transaction.receiver_id == receiver_id,
            Transaction.status == "deposited",
        ).first()

        if not tx:
            raise HTTPException(status_code=400, detail="No active deposited parcel for this receiver")

        locker = db.query(Locker).get(tx.locker_id)
        locker_mgr.open_locker(locker.number)

        _audit(
            db,
            user_id=receiver_id,
            role="receiver",
            receiver_id=receiver_id,
            locker_id=locker.id,
            parcel_status="collect_opened",
            action=f"Receiver opened Locker {locker.number}",
        )

        return {"ok": True, "locker_number": locker.number}
    finally:
        db.close()


@app.post("/api/collect/sensor_detect")
async def collect_sensor_detect(data: dict):
    """Confirm parcel removal using simulated or GPIO sensor."""
    locker_number = data.get("locker_number")
    locker_mgr.simulate_parcel_removed(locker_number)
    present = locker_mgr.detect_parcel(locker_number)
    return {"ok": True, "parcel_removed": not present}


@app.post("/api/collect/complete")
async def complete_collect(data: dict):
    """Confirm removal, close & lock locker, update transaction to Collected."""
    db = SessionLocal()
    try:
        receiver_id = data.get("receiver_id")
        tx_id = data.get("transaction_id")
        locker_number = data.get("locker_number")

        tx = db.query(Transaction).filter(
            Transaction.id == tx_id,
            Transaction.receiver_id == receiver_id,
            Transaction.status == "deposited",
        ).first()

        if not tx:
            raise HTTPException(status_code=400, detail="Invalid transaction or already collected")

        locker = db.query(Locker).get(tx.locker_id)

        # Hardware: close and lock locker
        locker_mgr.close_locker(locker.number)

        # Update database
        tx.status = "collected"
        tx.collected_at = dt.datetime.utcnow()
        locker.status = "available"
        locker.assigned_receiver_id = None
        db.commit()

        _audit(
            db,
            user_id=receiver_id,
            role="receiver",
            receiver_id=receiver_id,
            locker_id=locker.id,
            auth_result="success",
            parcel_status="collected",
            action=f"Parcel successfully collected from Locker {locker.number}",
        )

        return {
            "ok": True,
            "status": "collected",
            "locker_number": locker.number,
            "collected_at": tx.collected_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Locker Status & Audit Log Overview
# ---------------------------------------------------------------------------
@app.get("/api/lockers")
async def list_lockers():
    """List all lockers with live state."""
    db = SessionLocal()
    try:
        lockers = db.query(Locker).all()
        result = []
        for l in lockers:
            hw_state = locker_mgr.get_status(l.number)
            assigned_user = db.query(User).get(l.assigned_receiver_id) if l.assigned_receiver_id else None
            result.append({
                "id": l.id,
                "number": l.number,
                "status": l.status,
                "locked": hw_state["locked"],
                "parcel_present": hw_state["parcel_present"],
                "assigned_receiver": assigned_user.name if assigned_user else None,
            })
        return result
    finally:
        db.close()


@app.get("/api/audit-logs")
async def get_audit_logs(limit: int = 20):
    """Retrieve recent audit logs for system observability."""
    db = SessionLocal()
    try:
        logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
        return [
            {
                "id": log.id,
                "user_id": log.user_id,
                "role": log.role,
                "receiver_id": log.receiver_id,
                "locker_id": log.locker_id,
                "auth_result": log.auth_result,
                "parcel_status": log.parcel_status,
                "action": log.action,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
            }
            for log in logs
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Asynchronous Background AI Inference Worker (FTA Decoupled Pattern)
# ---------------------------------------------------------------------------
def _run_ai_inference_worker(
    frame: np.ndarray,
    mode: str,
    target_role: str,
    reg_frames: list,
    reg_positions: list,
) -> Dict[str, Any]:
    """Runs in background thread pool. Does NOT block video streaming loop."""
    reg_frames = list(reg_frames)
    reg_positions = [position.copy() for position in reg_positions]
    faces = face_engine.detect(frame)
    recognition_event = None
    duplicate_event = None
    reg_complete_event = None
    face_annotations = []
    is_failed_match = False
    spoof_detected = False
    liveness_scores = []

    for f in faces:
        x1, y1, x2, y2 = f["bbox"]
        emb = f["embedding"]
        qual = f["quality"]
        is_live, live_score = anti_spoofing.check_liveness(
            frame,
            np.asarray(f["bbox"], dtype=np.float32),
        )
        liveness_scores.append(live_score)

        if not is_live:
            spoof_detected = True
            face_annotations.append({
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "color": (0, 0, 255),
                "label": f"SPOOF BLOCKED ({live_score:.0%})",
            })
            continue

        if mode == "recognition":
            uid, sim = face_engine.recognize(emb)
            if uid is not None:
                color = (0, 230, 115)  # Green
                db = SessionLocal()
                try:
                    user = db.query(User).get(uid)
                    user_name = user.name if user else f"User #{uid}"
                    user_role = user.role if user else target_role
                    masked_phone = user.phone_masked if user else "***"
                    management_unit = user.management_unit if user else ""
                    external_id = user.external_id if user else ""

                    label = f"{user_name} ({sim:.0%})"
                    recognition_event = {
                        "user_id": uid,
                        "name": user_name,
                        "role": user_role,
                        "confidence": round(sim, 3),
                        "phone_masked": masked_phone,
                        "management_unit": management_unit,
                        "external_id": external_id,
                    }
                finally:
                    db.close()
            else:
                color = (0, 80, 255)  # Red / Orange
                label = f"Unknown ({sim:.0%})"
                is_failed_match = True

            face_annotations.append({
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "color": color,
                "label": f"{label} | Live {live_score:.0%}",
            })

        elif mode == "registration":
            is_good_quality = qual >= cfg.MIN_FACE_QUALITY
            color = (255, 200, 0) if is_good_quality else (0, 0, 255)
            label = f"Quality: {qual:.0%}"

            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2

            if is_good_quality and len(reg_frames) < cfg.REGISTRATION_FRAMES_REQUIRED:
                if len(reg_positions) == 0 or _moved_enough(reg_positions, [cx, cy]):
                    reg_frames.append(emb.copy())
                    reg_positions.append([cx, cy])

            face_annotations.append({
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "color": color,
                "label": f"Live {live_score:.0%} | {label}",
            })

    # Registration completion check
    if mode == "registration" and len(reg_frames) >= cfg.REGISTRATION_FRAMES_REQUIRED:
        avg_vec = np.mean(np.stack(reg_frames), axis=0).astype(np.float32)
        avg_vec /= np.linalg.norm(avg_vec) + 1e-12

        dup_id = face_engine.check_duplicate(avg_vec)
        if dup_id is not None:
            db = SessionLocal()
            try:
                dup_user = db.query(User).get(dup_id)
                dup_name = dup_user.name if dup_user else f"ID #{dup_id}"
                duplicate_event = {
                    "user_id": dup_id,
                    "name": dup_name,
                    "message": f"Face already registered in system (Belongs to: {dup_name})",
                }
            finally:
                db.close()
            reg_frames.clear()
            reg_positions.clear()
        else:
            reg_complete_event = {
                "embedding_hex": avg_vec.tobytes().hex(),
            }

    liveness_score = None
    if liveness_scores:
        liveness_score = min(liveness_scores) if spoof_detected else max(liveness_scores)

    return {
        "annotations": face_annotations,
        "recognition_event": recognition_event,
        "is_failed_match": is_failed_match and (recognition_event is None),
        "spoof_detected": spoof_detected,
        "liveness_score": liveness_score,
        "duplicate_event": duplicate_event,
        "reg_complete_event": reg_complete_event,
        "reg_captured": len(reg_frames),
        "reg_frames": reg_frames,
        "reg_positions": reg_positions,
        "quality": round(faces[0]["quality"], 2) if faces else 0.0,
    }


def _draw_overlay(frame: np.ndarray, annotations: list) -> np.ndarray:
    """Draw smooth bounding boxes & labels onto frame."""
    out = frame.copy()
    for ann in annotations:
        x1, y1, x2, y2 = ann["bbox"]
        color = ann["color"]
        label = ann["label"]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, label, (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out


def _moved_enough(positions: list, new_pos: list, min_dist: float = 12.0) -> bool:
    """Liveness motion verification: head center must move slightly."""
    if not positions:
        return True
    last = positions[-1]
    dist = ((new_pos[0] - last[0]) ** 2 + (new_pos[1] - last[1]) ** 2) ** 0.5
    return dist >= min_dist


# ---------------------------------------------------------------------------
# WebSocket: Real-Time Decoupled Edge Video Streaming (FTA Architecture)
# ---------------------------------------------------------------------------
@app.websocket("/ws/camera")
async def camera_ws(ws: WebSocket):
    """Stream the edge camera preview while running face AI in a worker thread."""
    await ws.accept()
    loop = asyncio.get_running_loop()

    mode = "idle"  # idle | recognition | registration
    target_role = "shipper"
    fail_count = 0
    reg_frames: List[np.ndarray] = []
    reg_positions: List[List[float]] = []
    ai_future = None
    ai_future_mode = None
    ai_future_generation = None
    mode_generation = 0
    latest_annotations = []
    latest_ai_time = 0.0
    recognition_interval = max(1, cfg.RECOGNITION_INTERVAL_FRAMES)
    frames_since_ai_dispatch = recognition_interval
    preview_interval = 1.0 / max(1, cfg.STREAM_PREVIEW_FPS)
    receive_task = asyncio.create_task(ws.receive_text())

    try:
        while True:
            if receive_task.done():
                raw = receive_task.result()
                receive_task = asyncio.create_task(ws.receive_text())
                msg = json.loads(raw)
                action = msg.get("action")

                if action == "start_recognition":
                    mode = "recognition"
                    target_role = msg.get("role", "shipper")
                    fail_count = 0
                    reg_frames.clear()
                    reg_positions.clear()
                    mode_generation += 1
                    latest_annotations = []
                    latest_ai_time = 0.0
                    frames_since_ai_dispatch = recognition_interval
                    logger.info("Camera WS: start_recognition for %s", target_role)

                elif action == "start_registration":
                    mode = "registration"
                    target_role = msg.get("role", "shipper")
                    fail_count = 0
                    reg_frames.clear()
                    reg_positions.clear()
                    mode_generation += 1
                    latest_annotations = []
                    latest_ai_time = 0.0
                    frames_since_ai_dispatch = recognition_interval
                    logger.info("Camera WS: start_registration for %s", target_role)

                elif action == "stop_camera":
                    mode = "idle"
                    mode_generation += 1
                    latest_annotations = []
                    latest_ai_time = 0.0
                    logger.info("Camera WS: stop_camera")

            payload_events = {}
            if ai_future and ai_future.done():
                try:
                    res = ai_future.result()
                    if ai_future_generation == mode_generation and ai_future_mode == mode:
                        latest_annotations = res["annotations"]
                        latest_ai_time = time.monotonic()

                        if mode == "recognition":
                            if res["spoof_detected"]:
                                payload_events["spoof_detected"] = True
                                payload_events["liveness_score"] = res["liveness_score"]
                            if res["recognition_event"]:
                                payload_events["recognized"] = res["recognition_event"]
                                fail_count = 0
                                db = SessionLocal()
                                try:
                                    _audit(
                                        db,
                                        user_id=res["recognition_event"]["user_id"],
                                        role=res["recognition_event"]["role"],
                                        auth_result="success",
                                        action=f"Face recognized: {res['recognition_event']['name']}",
                                    )
                                finally:
                                    db.close()
                            elif res["is_failed_match"]:
                                fail_count += 1
                                payload_events["fail_count"] = fail_count
                                payload_events["max_attempts"] = cfg.MAX_FAILED_ATTEMPTS
                                if fail_count >= cfg.MAX_FAILED_ATTEMPTS:
                                    payload_events["show_register"] = True

                        elif mode == "registration":
                            reg_frames = res["reg_frames"]
                            reg_positions = res["reg_positions"]
                            payload_events["reg_captured"] = res["reg_captured"]
                            payload_events["reg_required"] = cfg.REGISTRATION_FRAMES_REQUIRED
                            payload_events["quality"] = res["quality"]
                            payload_events["spoof_detected"] = res["spoof_detected"]
                            payload_events["liveness_score"] = res["liveness_score"]

                            if res["duplicate_event"]:
                                payload_events["duplicate"] = res["duplicate_event"]
                            elif res["reg_complete_event"]:
                                payload_events["registration_complete"] = True
                                payload_events["embedding_hex"] = res["reg_complete_event"]["embedding_hex"]
                                mode = "idle"
                                mode_generation += 1
                except Exception:
                    logger.exception("AI worker execution error")
                finally:
                    ai_future = None
                    ai_future_mode = None
                    ai_future_generation = None

            frame_started_at = time.monotonic()
            # CameraService captures frames on the same edge device as this backend.
            frame = camera_service.get_frame()
            if frame is None:
                await ws.send_json({"type": "status", "status": "camera_waiting"})
                await asyncio.sleep(preview_interval)
                continue

            frames_since_ai_dispatch += 1
            if (
                mode != "idle"
                and ai_future is None
                and frames_since_ai_dispatch >= recognition_interval
            ):
                ai_future = loop.run_in_executor(
                    ai_executor,
                    _run_ai_inference_worker,
                    frame.copy(),
                    mode,
                    target_role,
                    list(reg_frames),
                    [position.copy() for position in reg_positions],
                )
                ai_future_mode = mode
                ai_future_generation = mode_generation
                frames_since_ai_dispatch = 0

            max_stale_seconds = max(0, cfg.RECOGNITION_MAX_STALE_MS) / 1000
            if latest_ai_time and max_stale_seconds and (time.monotonic() - latest_ai_time) > max_stale_seconds:
                latest_annotations = []

            annotated = _draw_overlay(frame, latest_annotations)
            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 65])
            b64_img = base64.b64encode(buf).decode("ascii")

            payload = {
                "type": "frame",
                "image": f"data:image/jpeg;base64,{b64_img}",
                "mode": mode,
                **payload_events,
            }

            await ws.send_json(payload)
            await asyncio.sleep(max(0.0, preview_interval - (time.monotonic() - frame_started_at)))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket streaming error")
    finally:
        if not receive_task.done():
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=cfg.APP_HOST, port=cfg.APP_PORT, reload=False)
