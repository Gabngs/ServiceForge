from generador.settings import Settings
from generador.theme import build_stylesheet, status_colors


def test_settings_default():
    settings = Settings()
    assert settings.theme == "dark"


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    Settings(theme="light").save(path)

    loaded = Settings.load(path)
    assert loaded.theme == "light"


def test_settings_load_missing_file_returns_default(tmp_path):
    loaded = Settings.load(tmp_path / "does-not-exist.json")
    assert loaded.theme == "dark"


def test_settings_load_invalid_theme_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "neon"}', encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.theme == "dark"


def test_build_stylesheet_dark_and_light_differ():
    dark = build_stylesheet("dark")
    light = build_stylesheet("light")
    assert dark != light
    assert "#15161c" in dark
    assert "#f4f5f9" in light


def test_status_colors_has_all_states():
    colors = status_colors("light")
    assert set(colors.keys()) == {"idle", "busy", "ok", "error"}
