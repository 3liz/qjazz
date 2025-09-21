
from qjazz_cache.prelude import CacheManager
from qjazz_rpc import messages, op_requests
from qjazz_rpc.config import QgisConfig
from qjazz_rpc.worker import Feedback, Server

from .connection import Connection


def test_op_request_missing_target(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()

    conn = Connection()

    # Test Qgis server OWS request with valid project
    op_requests.handle_ows_request(
        conn,
        messages.OwsRequestMsg(
            service="WFS",
            request="GetCapabilities",
            target="",
            url="http://localhost:8080/test.3liz.com",
            header_prefix="x-test-",
            method=messages.HTTPMethod.GET,
            request_id="test_op_request_missing_target",
        ),
        qgis_server,
        cm,
        qgis_config,
        cache_id="test",
        feedback=feedback.feedback,
    )

    status, _ = conn.read_message()

    print("test_op_request_ows::status", status)
    assert status == 400


def test_op_request_invalid_target(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()

    conn = Connection()

    # Test Qgis server OWS request with valid project
    op_requests.handle_ows_request(
        conn,
        messages.OwsRequestMsg(
            service="WFS",
            request="GetCapabilities",
            target="/i_do_not_exists",
            url="http://localhost:8080/test.3liz.com",
            header_prefix="x-test-",
            method=messages.HTTPMethod.GET,
            request_id="test_op_request_invalid_target",
        ),
        qgis_server,
        cm,
        qgis_config,
        cache_id="test",
        feedback=feedback.feedback,
    )

    status, resp = conn.read_message()

    print("test_op_request_ows::status", status, resp)
    assert status == 403


def test_op_request_ows(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()

    conn = Connection()

    # Test Qgis server OWS request with valid project
    op_requests.handle_ows_request(
        conn,
        messages.OwsRequestMsg(
            service="WFS",
            request="GetCapabilities",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
            header_prefix="x-test-",
            method=messages.HTTPMethod.GET,
            request_id="test_op_request_ows",
        ),
        qgis_server,
        cm,
        qgis_config,
        cache_id="test",
        feedback=feedback.feedback,
    )

    status, resp = conn.read_message()

    print("test_op_request_ows::status", status)
    assert status == 200

    resp = messages.RequestReply.model_validate(resp)
    assert resp.status_code == 200
    assert resp.target == "/france/france_parts"

    print(f"> {resp.headers}")

    # Check header prefix
    for k, _ in resp.headers:
        assert k.startswith("x-test-")

    # Stream remaining bytes
    for chunk in conn.stream_bytes():
        assert len(chunk) > 0


def test_op_request_chunked_response(
    qgis_server: Server,
    feedback: Feedback,
    qgis_config: QgisConfig,
):
    """Test Response with chunk"""

    cm = CacheManager.get_service()

    conn = Connection()

    op_requests.handle_ows_request(
        conn,
        messages.OwsRequestMsg(
            service="WFS",
            request="GetFeature",
            version="1.0.0",
            options="SERVICE=WFS&REQUEST=GetFeature&TYPENAME=france_parts_bordure",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
            request_id="test_op_request_chunked_response",
        ),
        qgis_server,
        cm,
        qgis_config,
        cache_id="test",
        feedback=feedback.feedback,
    )

    status, resp = conn.read_message()
    print("test_op_request_chunked_response::status", status)
    assert status == 200

    resp = messages.RequestReply.model_validate(resp)
    assert resp.status_code == 200

    print("> headers", resp.headers)

    # Stream remaining bytes
    for chunk in conn.stream_bytes():
        assert len(chunk) > 0



