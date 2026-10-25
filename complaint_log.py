"""Complaint log: every send attempt (sent or failed) is appended to data/complaints.csv."""
import csv
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "data" / "complaints.csv"
COLUMNS = [
    "ref_id", "created_at", "department", "to_email", "severity", "latitude", "longitude",
    "location_source", "accuracy_m", "address", "landmark", "city", "language", "test_mode",
    "status", "error",
]


def append(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow({c: record.get(c, "") for c in COLUMNS})


def read_all() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
