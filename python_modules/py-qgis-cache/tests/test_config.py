""" Test configuration
"""
from urllib.parse import SplitResult


def test_search_paths(config):
    sp = config.search_paths
    for url in sp.values():
        assert isinstance(url, SplitResult)
        assert url.scheme, "Expecting scheme"
