from datetime import date, datetime, time, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo


VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def vietnamese_date_range(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=VIETNAM_TIMEZONE)
    return start, start + timedelta(days=1)


def distance_km(
    latitude: float,
    longitude: float,
    target_latitude: float,
    target_longitude: float,
) -> float:
    """Haversine distance between two WGS84 coordinate pairs."""
    lat1, lon1, lat2, lon2 = map(
        radians, (latitude, longitude, target_latitude, target_longitude)
    )
    lat_delta = lat2 - lat1
    lon_delta = lon2 - lon1
    value = (
        sin(lat_delta / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(lon_delta / 2) ** 2
    )
    return 6371.0088 * 2 * asin(sqrt(value))
