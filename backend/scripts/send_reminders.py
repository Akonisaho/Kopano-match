"""Send document expiry reminders now. Schedule it daily (Task Scheduler, cron).

Run from backend/:  python scripts/send_reminders.py

Each business hears once when a credential is within 30 days of expiry and once when it has
expired. Repeats are avoided using the audit log.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import reminders  # noqa: E402
from app.db import SessionLocal  # noqa: E402

if __name__ == "__main__":
    with SessionLocal() as db:
        result = reminders.run(db)
    print(f"Sent {result['notices_sent']} notices for {result['documents']} documents.")
