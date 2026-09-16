from pathlib import Path

from generador.fk_resolver import (
    FkResolutionCache,
    find_fk_candidates,
    resolve_fk,
)


def test_not_a_fk_column():
    base, candidates = find_fk_candidates("nombre", "siaw", ["siaw_roles"])
    assert base is None
    assert candidates == []


def test_single_match_auto_resolves():
    # Caso guía del documento: siaw_usuarios.rol_id -> siaw_roles (única coincidencia)
    tables = ["siaw_usuarios", "siaw_roles", "siaw_permisos"]
    base, candidates = find_fk_candidates("rol_id", "siaw", tables)
    assert base == "rol"
    assert candidates == ["siaw_roles"]


def test_ambiguous_two_candidates():
    tables = ["siaw_usuarios", "siaw_rol", "siaw_roles"]
    base, candidates = find_fk_candidates("rol_id", "siaw", tables)
    assert base == "rol"
    assert set(candidates) == {"siaw_rol", "siaw_roles"}


def test_zero_candidates_is_ambiguous():
    tables = ["siaw_usuarios"]
    base, candidates = find_fk_candidates("tienda_id", "siaw", tables)
    assert base == "tienda"
    assert candidates == []


def test_resolve_fk_auto():
    tables = ["siaw_usuarios", "siaw_roles"]
    cache = FkResolutionCache(path=Path("unused-in-this-test.json"))
    cache._data = {}  # no tocar disco
    resolution = resolve_fk(
        "rol_id", "siaw", tables, connection_id="test-conn", cache=cache
    )
    assert resolution.status == "auto"
    assert resolution.table == "siaw_roles"


def test_resolve_fk_ambiguous():
    tables = ["siaw_usuarios", "siaw_rol", "siaw_roles"]
    cache = FkResolutionCache(path=Path("unused-in-this-test.json"))
    cache._data = {}
    resolution = resolve_fk(
        "rol_id", "siaw", tables, connection_id="test-conn", cache=cache
    )
    assert resolution.status == "ambiguous"
    assert resolution.table is None
    assert set(resolution.candidates) == {"siaw_rol", "siaw_roles"}


def test_resolve_fk_not_a_fk_returns_none():
    cache = FkResolutionCache(path=Path("unused-in-this-test.json"))
    cache._data = {}
    resolution = resolve_fk(
        "nombre", "siaw", ["siaw_usuarios"], connection_id="test-conn", cache=cache
    )
    assert resolution is None


def test_cache_roundtrip(tmp_path):
    cache_path = tmp_path / "fk_resolutions.json"
    cache = FkResolutionCache(path=cache_path)
    cache.set("test-conn", "rol_id", "siaw_roles_custom")

    reloaded = FkResolutionCache(path=cache_path)
    assert reloaded.get("test-conn", "rol_id") == "siaw_roles_custom"
    assert reloaded.get("other-conn", "rol_id") is None


def test_resolve_fk_imported_mapping_wins_over_ambiguity(tmp_path):
    cache_path = tmp_path / "fk_resolutions.json"
    cache = FkResolutionCache(path=cache_path)

    tables = ["siaw_usuarios", "siaw_rol", "siaw_roles"]  # ambiguo sin el mapeo
    resolution = resolve_fk(
        "rol_id",
        "siaw",
        tables,
        connection_id="test-conn",
        cache=cache,
        imported_mapping={"rol_id": "siaw_roles"},
    )
    assert resolution.status == "from_mapping_file"
    assert resolution.table == "siaw_roles"


def test_resolve_fk_imported_mapping_wins_over_cache(tmp_path):
    cache_path = tmp_path / "fk_resolutions.json"
    cache = FkResolutionCache(path=cache_path)
    cache.set("test-conn", "rol_id", "siaw_roles_from_cache")

    resolution = resolve_fk(
        "rol_id",
        "siaw",
        ["siaw_usuarios", "siaw_roles"],
        connection_id="test-conn",
        cache=cache,
        imported_mapping={"rol_id": "siaw_roles_from_mapping"},
    )
    assert resolution.status == "from_mapping_file"
    assert resolution.table == "siaw_roles_from_mapping"


def test_cache_resolution_skips_ambiguity(tmp_path):
    cache_path = tmp_path / "fk_resolutions.json"
    cache = FkResolutionCache(path=cache_path)
    cache.set("test-conn", "rol_id", "siaw_roles")

    tables = ["siaw_usuarios", "siaw_rol", "siaw_roles"]  # ambiguo si no fuera por la caché
    resolution = resolve_fk(
        "rol_id", "siaw", tables, connection_id="test-conn", cache=cache
    )
    assert resolution.status == "resolved_from_cache"
    assert resolution.table == "siaw_roles"
