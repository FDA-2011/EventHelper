from database import db
from config import SEED_SPEAKERS, SEED_SCHEDULE, SEED_FAQ


def seed_if_empty():
    """Заполняет БД при первом запуске."""
    if not db.select("speakers"):
        for s in SEED_SPEAKERS:
            db.insert("speakers", s)

    if not db.select("locations"):
        for hall in {s["hall"] for s in SEED_SCHEDULE}:
            db.insert("locations", {"name": hall, "type": "hall"})

    if not db.select("tracks"):
        for track in {s["track"] for s in SEED_SCHEDULE}:
            db.insert("tracks", {"name": track})

    if not db.select("sessions"):
        for s in SEED_SCHEDULE:
            speaker = db.select("speakers", {"full_name": s["speaker"]})
            track = db.select("tracks", {"name": s["track"]})
            location = db.select("locations", {"name": s["hall"]})
            db.insert("sessions", {
                "title": s["title"],
                "start_time": s["start"],
                "end_time": s["end"],
                "speaker_id": speaker[0]["id"] if speaker else None,
                "track_id": track[0]["id"] if track else None,
                "location_id": location[0]["id"] if location else None,
            })

    if not db.select("faq"):
        for f in SEED_FAQ:
            db.insert("faq", f)