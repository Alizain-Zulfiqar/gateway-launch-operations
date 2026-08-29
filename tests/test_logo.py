"""tests/test_logo.py — Logo path resolution and availability tests."""


def test_logo_path_resolves():
    from config import LOGO_PATH, BASE_DIR
    assert str(BASE_DIR) in str(LOGO_PATH)


def test_logo_available_function():
    from config import logo_available, BASE_DIR
    result = logo_available()
    assert isinstance(result, bool)
    canonical = BASE_DIR / "assets" / "seagate_space_logo.png"
    if canonical.exists():
        assert result is True
