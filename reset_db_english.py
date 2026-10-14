"""Reset Smart Parcel Box database and FAISS index with English data and remove all prototype faces."""

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

import config as cfg
from database import init_db, SessionLocal, User, Locker, Transaction, AuditLog, engine, Base
from services.crypto import encrypt_embedding
import faiss

def reset_database():
    print("Resetting Smart Parcel Box database...")

    # 1. Close active connections & drop all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # 2. Reset FAISS index files
    idx_path = cfg.FAISS_DIR / "parcel_index.bin"
    map_path = cfg.FAISS_DIR / "parcel_map.npy"
    if idx_path.exists():
        idx_path.unlink()
    if map_path.exists():
        map_path.unlink()

    index = faiss.IndexFlatIP(512)
    id_map = []

    db = SessionLocal()
    try:
        # 3. Seed 6 Lockers
        for i in range(1, cfg.TOTAL_LOCKERS + 1):
            db.add(Locker(number=f"L{i:02d}", status="available"))
        db.commit()

        # 4. Seed English Receivers with synthetic dummy vectors (will NOT match any real human face)
        english_receivers = [
            {"name": "Alice Johnson", "phone": "0912345678", "unit": "Tower A - Horizon", "ext_id": "Apt 1204"},
            {"name": "Bob Williams", "phone": "0987654321", "unit": "Tower B - Horizon", "ext_id": "Apt 0802"},
            {"name": "David Miller", "phone": "0903456789", "unit": "Tower A - Horizon", "ext_id": "Apt 0511"},
            {"name": "Emma Davis", "phone": "0934567890", "unit": "Tower C - Horizon", "ext_id": "Apt 1506"},
            {"name": "Sophia Wilson", "phone": "0945678901", "unit": "Tower B - Horizon", "ext_id": "Apt 1102"},
        ]

        rng = np.random.RandomState(9999)
        for i, r in enumerate(english_receivers):
            # Generate random synthetic noise vector
            vec = rng.randn(512).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-12

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

            # Add to FAISS
            norm_vec = vec.reshape(1, -1)
            faiss.normalize_L2(norm_vec)
            index.add(norm_vec)
            id_map.append(u.id)

        # Save clean FAISS index
        faiss.write_index(index, str(idx_path))
        np.save(str(map_path), np.array(id_map, dtype=object))

        # Initial audit log
        db.add(AuditLog(
            action="system_initialized_english",
            auth_result="success",
            role="system",
        ))
        db.commit()

        print("Database successfully reset!")
        print(f"- Seeded {cfg.TOTAL_LOCKERS} lockers.")
        print(f"- Seeded {len(english_receivers)} sample receivers (Alice Johnson, Bob Williams, etc.)")
        print("- All previously trained faces (Tran Van An, person_001, person_002, etc.) have been completely removed from this database.")
        print("- You can now test face recognition as an unknown user and register directly via the web camera.")

    finally:
        db.close()

if __name__ == "__main__":
    reset_database()
