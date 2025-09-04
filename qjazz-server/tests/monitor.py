#
# Monitor that echo to stdout
#
import os
import sys

from io import BytesIO
from struct import unpack

from msgpack import unpackb

stdin_fileno = sys.stdin.fileno()

print(">>>> Starting MONITOR (test)")

while True:
    b = os.read(stdin_fileno, 4)
    # Take care if the parent close the connection then
    # read() will return an empty buffer (EOF)
    if b == b"":  # End of file: Parent closed the connection
        print("MONITOR: Connection closed by parent", file=sys.stderr)
        raise SystemExit(1)

    (size,) = unpack(">i", b)

    print(">>>>", size)
    data = os.read(stdin_fileno, size)

    # Handle data larger than pipe size
    if len(data) < size:
        buf = BytesIO()
        buf.write(data)
        remaining = size - len(data)
        while remaining > 0:
            chunk = os.read(stdin_fileno, remaining)
            remaining -= len(chunk)
            buf.write(chunk)
        data = buf.getvalue()

    msg = unpackb(data)
    print(">>>>", msg)

