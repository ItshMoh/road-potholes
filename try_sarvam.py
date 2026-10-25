"""Terminal check of the AI chain (milestone M1).

Usage: .venv/bin/python try_sarvam.py test_photos/pothole1.jpg test_photos/cat.jpg ...

Every photo is checked with gemma4. For the first pothole photo, the complaint is written with
sarvam-105b and translated to Hindi and Hinglish with mayura:v1.
"""
import sys
from datetime import datetime

from location import IST, PHOTO_GPS, format_location_block, gps_from_photo
from photo import resize_photo
from sarvam_client import HINGLISH, SarvamError, check_pothole, translate, write_complaint


def main(paths: list[str]) -> None:
    letter_done = False
    for path in paths:
        print(f"\n===== {path} =====")
        with open(path, "rb") as f:
            raw = f.read()
        gps = gps_from_photo(raw)
        print("Photo GPS:", gps or "none")

        check = check_pothole(resize_photo(raw))
        print("Check:", check)
        if not check["is_pothole"] or letter_done:
            continue
        letter_done = True

        facts = {
            "description": check["description"],
            "severity": check["severity"],
            "address": "Lanka Road",
            "landmark": "Near Lanka Gate, BHU",
            "city": "Varanasi",
            "pin": "221005",
            "reported_at": datetime.now(IST).strftime("%d %b %Y %H:%M IST"),
            "department": "Varanasi Nagar Nigam – Roads (Engineering Department)",
            "reporter_name": "Test Reporter",
            "reporter_phone": "9876543210",
        }
        letter = write_complaint(facts)
        print("\n--- Subject ---\n" + letter["subject"])
        print("\n--- Body ---\n" + letter["body"])
        print("\n--- Hindi ---\n" + translate(letter["body"], "hi-IN"))
        print("\n--- Hinglish ---\n" + translate(letter["body"], HINGLISH))
        print("\n" + format_location_block({**facts, "pothole": gps, "pothole_source": PHOTO_GPS, "device": None}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        main(sys.argv[1:])
    except SarvamError as e:
        sys.exit(f"Sarvam error: {e}")
