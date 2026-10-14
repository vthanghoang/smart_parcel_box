"""SQLAlchemy models and session factory."""

import datetime as _dt

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, LargeBinary,
    DateTime, ForeignKey, Text, create_engine, func,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # shipper | receiver
    management_unit = Column(String(200), nullable=True)
    external_id = Column(String(50), nullable=True)  # shipper_id or room_id
    face_embedding_enc = Column(LargeBinary, nullable=False)  # Fernet-encrypted
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    transactions_as_shipper = relationship(
        "Transaction", foreign_keys="Transaction.shipper_id", back_populates="shipper",
    )
    transactions_as_receiver = relationship(
        "Transaction", foreign_keys="Transaction.receiver_id", back_populates="receiver",
    )

    @property
    def phone_masked(self) -> str:
        if len(self.phone) >= 3:
            return "***" + self.phone[-3:]
        return "***"


class Locker(Base):
    __tablename__ = "lockers"
    id = Column(Integer, primary_key=True)
    number = Column(String(10), unique=True, nullable=False)
    status = Column(String(20), default="available")  # available | occupied | maintenance
    assigned_receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    transactions = relationship("Transaction", back_populates="locker")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    shipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    locker_id = Column(Integer, ForeignKey("lockers.id"), nullable=False)
    status = Column(String(20), default="deposited")  # deposited | collected | expired
    deposited_at = Column(DateTime, default=func.now())
    collected_at = Column(DateTime, nullable=True)

    shipper = relationship("User", foreign_keys=[shipper_id], back_populates="transactions_as_shipper")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="transactions_as_receiver")
    locker = relationship("Locker", back_populates="transactions")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    role = Column(String(20), nullable=True)
    receiver_id = Column(Integer, nullable=True)
    locker_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=func.now())
    auth_result = Column(String(20), nullable=True)  # success | failed | registered
    parcel_status = Column(String(20), nullable=True)
    action = Column(Text, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
