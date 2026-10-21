from datetime import datetime
import sys
import os

_COMMON_DT_FORMATS = (  "%Y-%m-%dT%H:%M:%S.%fZ",    #2026-10-15T14:30:45.123456Z
                        "%Y-%m-%dT%H:%M:%SZ",       #2026-10-15T14:30:45Z
                        "%Y-%m-%dT%H:%M:%S.%f",     #2026-10-15T14:30:45.123456
                        "%Y-%m-%dT%H:%M:%S",        #2026-10-15T14:30:45
                        "%Y-%m-%d %H:%M:%S",        #2026-10-15 14:30:45
                        "%d.%m.%Y %H:%M:%S",        #15.10.2026 14:30:45
                        "%m/%d/%Y %H:%M:%S",  )     #10/15/2025 14:30:45

def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except (TypeError, ValueError):
        return False

def parse_any_datetime(value: str | None) -> datetime:
    if value is None:
        raise ValueError("Datetime value is None")

    s = str(value).strip()
    if not s:
        raise ValueError("Empty datetime string")

    if is_int(s):           #1792074645 seconds
        iv = int(s)
        if iv >= 10**12:    #1792074645000 milliseconds
            iv //= 1000
        return datetime.fromtimestamp(iv)

    for fmt in _COMMON_DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(s.rstrip("Z")) #2026-10-15T14:30:45+02:00 or 2026-10-15T14:30Z
    except ValueError:
        raise ValueError(f"Unrecognized datetime format: {value!r}")

def split_date_time(dt: datetime) -> tuple[str, str]:
    if not isinstance(dt, datetime):
        raise ValueError("dt must be an datetime object")

    return ( dt.strftime("%Y.%m.%d"), # %d.%m.%Y had caused a listing bug since SQL query sorts lexicographically
             dt.strftime("%H:%M:%S") )







