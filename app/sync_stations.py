"""Scheduled observations for explicitly configured stations."""

import argparse
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import SessionLocal
from app.integrations.inmet import InmetError
from app.integrations.stations import fetch_observations, observation
from app.station_models import WeatherStation
from app.station_sync import save_latest, save_observations


def sync_once():
    settings = get_settings()
    today = datetime.now(UTC).date()
    ok = True
    for code in settings.inmet_station_codes:
        with SessionLocal() as db:
            try:
                records = fetch_observations(code, today - timedelta(days=1), today)
                rows = []
                for row in records:
                    try:
                        meta, values = observation(row)
                        if (
                            meta["code"] == code
                            and today - timedelta(days=1) <= values["observed_at"].date() <= today
                        ):
                            rows.append((meta, values))
                    except (ValueError, TypeError, AttributeError):
                        continue
                inserted, updated = save_observations(db, rows)
                item = db.get(WeatherStation, code)
                if not rows and item:
                    inserted, updated = save_latest(db, item)
                db.commit()
                print(f"{code}: {inserted} novas, {updated} atualizadas", flush=True)
            except (InmetError, SQLAlchemyError, ValueError) as error:
                db.rollback()
                print(
                    f"{code}: falha na consulta; dados preservados ({type(error).__name__})",
                    flush=True,
                )
                ok = False
    return ok


def main():
    parser = argparse.ArgumentParser(description="Sincroniza observações de estações INMET")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    while True:
        ok = sync_once() if settings.inmet_observations_enabled else False
        if not args.loop:
            raise SystemExit(0 if ok else 1)
        time.sleep(settings.inmet_sync_interval_minutes * 60)


if __name__ == "__main__":
    main()
