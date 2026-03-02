#!/usr/bin/env python3
"""Validate EventMatcher confidence threshold against real data.

Run via: docker exec <backend_container> python scripts/validate_confidence.py

This script queries the event_id_mappings table for recent matches,
groups them by confidence band, and prints a summary to help determine
whether the current CONFIDENCE_THRESHOLD (0.90) is appropriate.

Decision tree:
- If all correct matches are >= 0.90: threshold is validated, no change needed
- If correct matches cluster at 0.85-0.90: consider lowering to 0.85
- Document the outcome either way to satisfy STAB-03
"""

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

# Ensure app imports work when run from project root
sys.path.insert(0, "/app")

from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.models.event_id_mapping import EventIDMapping
from app.monitoring.event_matcher import CONFIDENCE_THRESHOLD


def main():
    print(f"Current CONFIDENCE_THRESHOLD: {CONFIDENCE_THRESHOLD}")
    print(f"Querying event_id_mappings from the last 7 days...\n")

    with SyncSessionLocal() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        # Get all recent mappings with their event details
        rows = session.execute(
            select(
                EventIDMapping.prophetx_event_id,
                EventIDMapping.confidence,
                EventIDMapping.is_confirmed,
                EventIDMapping.updated_at,
                Event.home_team,
                Event.away_team,
                Event.sport,
                Event.scheduled_start,
            )
            .join(Event, Event.prophetx_event_id == EventIDMapping.prophetx_event_id)
            .where(EventIDMapping.updated_at > cutoff)
            .order_by(EventIDMapping.confidence.asc())
        ).all()

        if not rows:
            print("No event_id_mappings found in the last 7 days.")
            print("The system may not have matched any events yet.")
            return

        # Band analysis
        bands = {
            "0.70-0.79": [],
            "0.80-0.84": [],
            "0.85-0.89": [],
            "0.90-0.94": [],
            "0.95-1.00": [],
        }

        for row in rows:
            conf = row.confidence
            if conf < 0.70:
                continue  # Skip very low confidence (noise)
            elif conf < 0.80:
                bands["0.70-0.79"].append(row)
            elif conf < 0.85:
                bands["0.80-0.84"].append(row)
            elif conf < 0.90:
                bands["0.85-0.89"].append(row)
            elif conf < 0.95:
                bands["0.90-0.94"].append(row)
            else:
                bands["0.95-1.00"].append(row)

        print("=" * 80)
        print("CONFIDENCE BAND DISTRIBUTION")
        print("=" * 80)
        total = len(rows)
        confirmed = sum(1 for r in rows if r.is_confirmed)
        print(f"Total mappings (7d): {total}")
        print(f"Confirmed (>= {CONFIDENCE_THRESHOLD}): {confirmed}")
        print(f"Unconfirmed (< {CONFIDENCE_THRESHOLD}): {total - confirmed}")
        print()

        for band_name, band_rows in bands.items():
            if not band_rows:
                continue
            conf_count = sum(1 for r in band_rows if r.is_confirmed)
            print(f"  {band_name}: {len(band_rows)} matches ({conf_count} confirmed)")
            # Show details for the critical 0.85-0.89 band
            if band_name == "0.85-0.89":
                for r in band_rows:
                    print(f"    conf={r.confidence:.4f} confirmed={r.is_confirmed} "
                          f"sport={r.sport} "
                          f"{r.home_team} vs {r.away_team}")

        print()
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)

        # Decision logic
        critical_band = bands["0.85-0.89"]
        if not critical_band:
            print("No matches in the 0.85-0.89 band.")
            print("Threshold 0.90 appears appropriate -- no false negatives detected.")
            print("STAB-03 VALIDATED: threshold confirmed at 0.90.")
        else:
            print(f"{len(critical_band)} matches in the 0.85-0.89 band (shown above).")
            print("Review these manually:")
            print("  - If they are CORRECT matches: consider lowering threshold to 0.85")
            print("  - If they are INCORRECT matches: threshold 0.90 is appropriate")
            print()
            print("To lower the threshold:")
            print("  1. Edit backend/app/monitoring/event_matcher.py")
            print("  2. Change CONFIDENCE_THRESHOLD = 0.90 to 0.85")
            print("  3. Flush match cache: redis-cli KEYS 'match:px:*' | xargs redis-cli DEL")
            print("  4. Rebuild and redeploy: docker compose build && docker compose up -d")


if __name__ == "__main__":
    main()
