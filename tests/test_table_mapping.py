from generador.table_mapping import (
    load_mapping_md,
    parse_mapping_md,
    render_mapping_md,
    save_mapping_md,
)

SAMPLE_MD = """\
# Mapeo de relaciones — db_gsp_siaw

Notas sueltas que no son parte de la tabla, no deberían romper el parseo.

| Columna | Tabla |
|---|---|
| tienda_id | catalogo_tienda |
| rol_id | siaw_roles |
| cargo_id | sip_personalcargos |
"""


def test_parse_mapping_md_basic():
    result = parse_mapping_md(SAMPLE_MD)
    assert result == {
        "tienda_id": "catalogo_tienda",
        "rol_id": "siaw_roles",
        "cargo_id": "sip_personalcargos",
    }


def test_parse_mapping_md_ignores_header_and_separator():
    result = parse_mapping_md("| Columna | Tabla |\n|---|---|\n| x_id | tabla_x |\n")
    assert result == {"x_id": "tabla_x"}


def test_parse_mapping_md_ignores_non_table_lines():
    result = parse_mapping_md("Solo texto libre\nsin ninguna tabla\n")
    assert result == {}


def test_parse_mapping_md_strips_backticks_and_whitespace():
    result = parse_mapping_md("| `tienda_id` |  catalogo_tienda  |\n")
    assert result == {"tienda_id": "catalogo_tienda"}


def test_render_mapping_md_roundtrip():
    mapping = {"rol_id": "siaw_roles", "tienda_id": "catalogo_tienda"}
    rendered = render_mapping_md(mapping, title="Mi mapeo")
    assert "# Mi mapeo" in rendered
    reparsed = parse_mapping_md(rendered)
    assert reparsed == mapping


def test_render_mapping_md_sorted_deterministic():
    mapping = {"z_id": "tabla_z", "a_id": "tabla_a"}
    rendered = render_mapping_md(mapping)
    assert rendered.index("a_id") < rendered.index("z_id")


def test_save_and_load_mapping_md(tmp_path):
    mapping = {"rol_id": "siaw_roles"}
    path = tmp_path / "nested" / "mapeo.md"
    saved_path = save_mapping_md(mapping, path)
    assert saved_path == path
    assert path.exists()

    loaded = load_mapping_md(path)
    assert loaded == mapping
