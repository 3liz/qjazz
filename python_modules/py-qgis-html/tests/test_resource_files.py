import importlib.resources


def test_resource_files():

    root = importlib.resources.files("py_qgis_html") / "html"
    assert root.exists()

    path = root.joinpath("bootstrap")
    assert path.is_dir()

    path = root.joinpath("octicons")
    assert path.is_dir()

    path = root.joinpath("assets")
    assert path.is_dir()

    path = root.joinpath("assets", "popper.min.js")
    assert path.is_file()
