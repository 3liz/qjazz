
from time import time
from typing import Optional

from .cachemanager import (
    CacheEntry,
    CacheManager,
)
from .cachemanager import (
    CheckoutStatus as Co,
)

#
# Cache eviction strategy
#


def evict_by_popularity(cm: CacheManager) -> Optional[CacheEntry]:
    """ Evict a project from cache based on
        its `popularity`

        Returns `true` if object has been evicted from the
        cache, `false` otherwise.
    """
    # Evaluate an euristics based on last_hit timestamp
    # and hits number
    # This is simple model of cache frequency eviction.
    # Such model is related to `hyperbolic policy`:
    # https://www.usenix.org/system/files/conference/atc17/atc17-blankstein.pdf
    # Where eviction scheme is based on popularity over a time period.
    #
    # Here we take the number of hits divided by the  lifetime period
    # of the object in cache
    #
    # This should be ok as long the rate of insertion of new object is low
    # which we assume is the case for this kind of resource.
    now = time()

    candidate = min(
        (e for e in cm.iter() if not e.pinned),
        default=None,
        key=lambda e: e.hits / (now - e.timestamp),
    )

    if candidate:
        cm.update(candidate.md, Co.REMOVED)

    return candidate
