import paperpi


def test_version_is_v2():
    assert paperpi.__version__.startswith("2.")
