"""Seed initial lockers, receivers, and a sample parcel transaction."""

import os
import sys
from pathlib import Path
import numpy as np

# Ensure root import
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import TOTAL_LOCKERS
from database import init_db, SessionLocal, User, Locker, Transaction, AuditLog
from services.crypto import encrypt_embedding
from services.face_engine import face_engine
from services.locker_manager import locker_mgr

def seed():
    init_db()
    db = SessionLocal()
    try:
        # 1. Seed Lockers
        for i in range(1, TOTAL_LOCKERS + 1):
            num = f"L{i:02d}"
            locker = db.query(Locker).filter(Locker.number == num).first()
            if not locker:
                locker = Locker(number=num, status="available")
                db.add(locker)
        db.commit()

        # 2. Check if users already seeded
        existing_users = db.query(User).count()
        if existing_users == 0:
            print("Seeding initial users and receivers...")

            # Load embeddings prototype if available, else generate normalized dummy vectors
            prototypes = None
            npz_path = Path(__file__).resolve().parent.parent / "insightface" / "artifacts" / "embeddings.npz"
            if npz_path.exists():
                try:
                    npz = np.load(str(npz_path))
                    prototypes = npz.get("prototypes")
                    print(f"Loaded {len(prototypes)} prototypes from {npz_path}")
                except Exception as e:
                    print(f"Could not load prototypes: {e}")

            def get_vector(idx: int) -> np.ndarray:
                if prototypes is not None and idx < len(prototypes):
                    vec = prototypes[idx].astype(np.float32)
                else:
                    rng = np.random.RandomState(42 + idx)
                    vec = rng.randn(512).astype(np.float32)
                vec /= np.linalg.norm(vec) + 1e-12
                return vec

            # Sample Receivers
            receivers_data = [
                {"name": "Nguyễn Văn An", "phone": "0912345678", "unit": "Tòa A - Golden Land", "ext_id": "P-1204"},
                {"name": "Trần Thị Bình", "phone": "0987654321", "unit": "Tòa B - Golden Land", "ext_id": "P-0802"},
                {"name": "Lê Hoàng Cường", "phone": "0903456789", "unit": "Tòa A - Golden Land", "ext_id": "P-0511"},
                {"name": "Phạm Minh Đức", "phone": "0934567890", "unit": "Tòa C - Golden Land", "ext_id": "P-1506"},
                {"name": "Vũ Mai Hương", "phone": "0945678901", "unit": "Tòa B - Golden Land", "ext_id": "P-1102"},
            ]

            created_receivers = []
            for i, r in enumerate(receivers_data):
                vec = get_vector(i)
                raw_bytes = vec.tobytes()
                enc_bytes = encrypt_embedding(raw_bytes)
                u = User(
                    name=r["name"],
                    phone=r["phone"],
                    role="receiver",
                    management_unit=r["unit"],
                    external_id=r["ext_id"],
                    face_embedding_enc=enc_bytes,
                )
                db.add(u)
                db.commit()
                db.refresh(u)
                created_receivers.append((u, vec))

            # Sample Shipper
            shipper_vec = get_vector(5)
            shipper_raw = shipper_vec.tobytes()
            shipper_user = User(
                name="Trần Văn Giao",
                phone="0977112233",
                role="shipper",
                management_unit="Giao Hàng Tiết Kiệm (GHTK)",
                external_id="SHIP-8899",
                face_embedding_enc=encrypt_embedding(shipper_raw),
            )
            db.add(shipper_user)
            db.commit()
            db.refresh(shipper_user)

            # Re-index faces in FAISS
            face_engine.initialize()
            for u, vec in created_receivers:
                face_engine.add_face(u.id, vec)
            face_engine.add_face(shipper_user.id, shipper_vec)
            face_engine.save_index()

            # 3. Seed one active parcel for receiver Nguyễn Văn An (in Locker L02) for testing pickup
            rec_an = created_receivers[0][0]
            locker_2 = db.query(Locker).filter(Locker.number == "L02").first()
            if locker_2:
                locker_2.status = "occupied"
                locker_2.assigned_receiver_id = rec_an.id
                tx = Transaction(
                    shipper_id=shipper_user.id,
                    receiver_id=rec_an.id,
                    locker_id=locker_2.id,
                    status="deposited",
                )
                db.add(tx)
                db.commit()
                # mock hardware parcel in L02
                locker_mgr.simulate_parcel_placed("L02")

                # Audit log
                db.add(AuditLog(
                    user_id=shipper_user.id,
                    role="shipper",
                    receiver_id=rec_an.id,
                    locker_id=locker_2.id,
                    auth_result="success",
                    parcel_status="deposited",
                    action="seed_sample_parcel",
                ))
                db.commit()
                print("Seeded sample active deposited parcel in Locker L02 for receiver Nguyễn Văn An.")

        print("Database seeding completed successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
