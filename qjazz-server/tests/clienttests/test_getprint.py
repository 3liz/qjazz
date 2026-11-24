"""
    Test WMS GetPrint requests

    Check that printed documents are returned complete
    (see https://projects.3liz.org/infra/infra-doc/-/work_items/3126)
"""
import requests

PRINT_PARAMS = {
    'MAP': '/montpellier/montpellier.qgs',
    'SERVICE': 'WMS',
    'REQUEST': 'GetPrint',
    'VERSION': '1.3.0',
    'TEMPLATE': 'Landscape A4',
    'CRS': 'EPSG:3857',
    'map0:EXTENT': '430000,5400000,440000,5410000',
}


def check_content_length(rv: requests.Response) -> None:
    content_length = rv.headers.get('Content-Length')
    if content_length is not None:
        assert int(content_length) == len(rv.content)


def check_pdf(rv: requests.Response) -> None:
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'application/pdf'
    check_content_length(rv)

    data = rv.content
    assert data.startswith(b'%PDF-')
    # A truncated document has no end-of-file marker
    assert data.rstrip().endswith(b'%%EOF')
    assert b'startxref' in data[-1024:]


def test_getprint_pdf(backend: str) -> None:
    """Test that the pdf document is complete"""
    rv = requests.get(f"{backend}/", params={**PRINT_PARAMS, 'FORMAT': 'pdf'})
    print("\ntest_getprint_pdf::size", len(rv.content))
    check_pdf(rv)


def test_getprint_pdf_post(backend: str) -> None:
    """Test GetPrint as urlencoded form"""
    rv = requests.post(
        f"{backend}/",
        data={**PRINT_PARAMS, 'FORMAT': 'pdf'},
        headers={'x-request-id': 'test_getprint_pdf_post'},
    )
    check_pdf(rv)


def test_getprint_pdf_repeated(backend: str) -> None:
    """Test that successive prints return identical sizes

    Detect partial writes depending on worker state
    """
    sizes = set()
    for _ in range(4):
        rv = requests.get(f"{backend}/", params={**PRINT_PARAMS, 'FORMAT': 'pdf'})
        check_pdf(rv)
        sizes.add(len(rv.content))
    print("\ntest_getprint_pdf_repeated::sizes", sizes)
    # Documents may differ by metadata (i.e creation date)
    # but not by an order of magnitude
    assert max(sizes) - min(sizes) < 1024


def test_getprint_png(backend: str) -> None:
    """Test that the png image is complete"""
    rv = requests.get(f"{backend}/", params={**PRINT_PARAMS, 'FORMAT': 'png'})
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'image/png'
    check_content_length(rv)

    data = rv.content
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    # Last chunk must be IEND (4 bytes length + 'IEND' + 4 bytes crc)
    assert data[-8:-4] == b'IEND'


def test_getprint_invalid_template(backend: str) -> None:
    """Test that an invalid template returns an OWS exception"""
    rv = requests.get(
        f"{backend}/",
        params={**PRINT_PARAMS, 'FORMAT': 'pdf', 'TEMPLATE': 'NoSuchLayout'},
    )
    assert rv.status_code == 400
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'
    assert b'<ServiceExceptionReport' in rv.content
    assert b'TEMPLATE' in rv.content
