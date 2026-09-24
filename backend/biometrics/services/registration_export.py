"""Append non-sensitive registration records outside the relational database."""

from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from django.conf import settings

_lock = Lock()
_FIELDS = ("customer_id", "full_name", "mobile_number", "registered_at", "enrollment_status")


def append_registration(customer) -> None:
    """Write one registration row without PINs, hashes, media, or templates.

    The temporary-file replacement keeps the export valid if the process stops
    while creating a new file. Appends are serialized within this backend
    process; the database remains the source of truth for authentication.
    """
    destination = Path(settings.REGISTRATION_CSV_PATH).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        existing = destination.exists() and destination.stat().st_size > 0
        with destination.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=_FIELDS)
            if not existing:
                writer.writeheader()
            writer.writerow(
                {
                    "customer_id": str(customer.customer_id),
                    "full_name": customer.full_name,
                    "mobile_number": customer.mobile_number,
                    "registered_at": datetime.now(UTC).isoformat(),
                    "enrollment_status": customer.biometric_user.enrollment_status,
                }
            )
            stream.flush()
            os.fsync(stream.fileno())


def export_existing_customers(customers, destination: Path) -> int:
    """Create a one-time CSV snapshot before an explicitly requested reset."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "customer_id": str(customer.customer_id),
            "full_name": customer.full_name,
            "mobile_number": customer.mobile_number,
            "registered_at": customer.created_at.isoformat(),
            "enrollment_status": customer.biometric_user.enrollment_status,
        }
        for customer in customers.select_related("biometric_user").order_by("created_at")
    ]
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    return len(rows)
