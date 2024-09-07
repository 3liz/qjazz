import pytest

from py_qgis_rpc import messages

pytest_plugins = ('pytest_asyncio',)


async def test_async_pipe_io():
    """ Test asynchronous pipe
    """
    parent, child = messages.Pipe.new()

    child.send("Hello World")

    response = await parent.read(timeout=10)
    assert response == "Hello World"


async def test_async_read_timeout():
    """ Test asynchronous pipe
    """
    parent, _ = messages.Pipe.new()

    with pytest.raises(messages.WouldBlockError):
        await parent.read(timeout=1)
