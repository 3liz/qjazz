# Cache status
#
# Defined in its own module for preventing us to import
# QGIS stuff
#

from enum import Enum


class CheckoutStatus(Enum):
    """Returned as checkout result from
    CacheManager.
    Gives information about the status
    of the required resource.
    """

    UNCHANGED = 0
    NEEDUPDATE = 1
    REMOVED = 2
    NOTFOUND = 3
    NEW = 4
    # Returned by update() if the resource
    # has been updated on NEEDUPDATE.
    UPDATED = 5
