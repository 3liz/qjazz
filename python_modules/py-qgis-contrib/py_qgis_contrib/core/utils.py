""" Various utility functions
"""
from datetime import datetime, timezone

from typing_extensions import Literal

#
# RFC822 datetime format
#

WEEKDAYS = [
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
]


def to_rfc822(timestamp):
    """ Convert timestamp in seconds
        to rfc 822 Last-Modified HTTP format
    """
    dt = datetime.fromtimestamp(timestamp).astimezone(timezone.utc)
    dayname = WEEKDAYS[dt.weekday()]
    return (
        f"{dayname}, {dt.day:02} {dt.month:02} {dt.year:04} "
        f"{dt.hour:02}:{dt.minute:02}:{dt.second:02} GMT"
    )


def to_iso8601(
    dt: datetime,
    timespec: Literal[
        'auto',
        'hours',
        'minutes',
        'seconds',
        'milliseconds',
    ] = 'milliseconds',
) -> str:
    """ convert datetime to iso 8601 (UTC)
    """
    return dt.astimezone(timezone.utc).isoformat(timespec=timespec)


def utc_now() -> datetime:
    """ Return the actuel UTC datetime the correct UTC
        timezone - which is NOT what `datetime.utcnow()` do.
    """
    return datetime.now(timezone.utc)
