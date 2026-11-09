from sqlalchemy import select

from app.integrations.stations import fetch_latest, observation
from app.station_models import StationObservation, WeatherStation


def save_station(db, values):
    item = db.get(WeatherStation, values["code"])
    if item is None:
        item = WeatherStation(**values)
        db.add(item)
    else:
        for key, value in values.items():
            # A historical export without metadata must not erase the live catalog.
            if value is not None and not (key == "name" and value == values["code"]):
                setattr(item, key, value)
    db.flush()
    return item


def save_observations(db, rows):
    """Idempotent natural key; the caller owns the transaction."""
    inserted = updated = 0
    for meta, values in rows:
        save_station(db, meta)
        item = db.scalar(
            select(StationObservation).where(
                StationObservation.station_code == values["station_code"],
                StationObservation.observed_at == values["observed_at"],
                StationObservation.period == values["period"],
            )
        )
        if item is None:
            db.add(StationObservation(**values))
            inserted += 1
        else:
            for key, value in values.items():
                if value is not None:
                    setattr(item, key, value)
            updated += 1
        db.flush()
    return inserted, updated


def save_latest(db, item):
    """Store the station's latest measurement; the caller owns the transaction.

    INMET answers with the nearest reporting station, which may be another one (a station
    out of order, for example). Those values must not be attributed to this station.
    """
    if not item.geocode:
        return 0, 0
    row = fetch_latest(item.geocode)
    if not row:
        return 0, 0
    try:
        meta, values = observation(row)
    except (ValueError, TypeError, AttributeError):
        return 0, 0
    if meta["code"] != item.code:
        return 0, 0
    return save_observations(db, [(meta, values)])
