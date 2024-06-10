
import sys

if sys.version_info >= (3, 11):
    from asyncio import timeout as deadline
else:
    from async_timeout import timeout as deadline  # noqa F401
