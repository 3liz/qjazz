""" Various utility functions
"""
from datetime import datetime, timezone

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
