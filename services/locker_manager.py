"""Mock locker manager (replace internals with RPi.GPIO for deployment)."""

from __future__ import annotations

import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)


class LockerManager:
    """Simulates locker hardware. On Raspberry Pi, replace _hw_* methods with GPIO calls."""

    def __init__(self, total: int = 6):
        # state: locker_number -> {"locked": bool, "parcel_present": bool}
        self._state: Dict[str, dict] = {}
        for i in range(1, total + 1):
            self._state[f"L{i:02d}"] = {"locked": True, "parcel_present": False}

    def open_locker(self, number: str) -> bool:
        if number not in self._state:
            return False
        self._state[number]["locked"] = False
        logger.info("Locker %s OPENED", number)
        # GPIO: set relay pin HIGH
        return True

    def close_locker(self, number: str) -> bool:
        if number not in self._state:
            return False
        self._state[number]["locked"] = True
        logger.info("Locker %s CLOSED & LOCKED", number)
        # GPIO: set relay pin LOW
        return True

    def is_locked(self, number: str) -> bool:
        return self._state.get(number, {}).get("locked", True)

    def detect_parcel(self, number: str) -> bool:
        """Check sensor for parcel presence. Returns True if parcel detected."""
        # Mock: read IR / weight sensor via GPIO
        return self._state.get(number, {}).get("parcel_present", False)

    def simulate_parcel_placed(self, number: str):
        """Dev helper: simulate placing a parcel."""
        if number in self._state:
            self._state[number]["parcel_present"] = True

    def simulate_parcel_removed(self, number: str):
        """Dev helper: simulate removing a parcel."""
        if number in self._state:
            self._state[number]["parcel_present"] = False

    def get_status(self, number: str) -> dict:
        s = self._state.get(number, {})
        return {"number": number, "locked": s.get("locked", True), "parcel_present": s.get("parcel_present", False)}


locker_mgr = LockerManager()
