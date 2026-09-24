"""Mapa del proyecto en notas .md con wikilinks (relation_map.py)."""

import pytest

from generador import layout, relation_map
from generador.layout import STANDARD_LAYOUT, RolePlacement
from generador.relation_map import ClassRef, RelationMap

TIPO = "App\\Http\\Resources\\dbsiaw\\catalogo_tiposistemaRelationResource"
TIPO_PATH = "app/Http/Resources/dbsiaw/catalogo_tiposistemaRelationResource.php"


def test_project_key_uses_the_folder_name_so_it_survives_another_pc():
    assert relation_map.project_key("C:/Users/a/Documents/siaw-laravel-backend") == "siaw-laravel-backend"
    assert relation_map.project_key("/home/b/code/siaw-laravel-backend") == "siaw-laravel-backend"
    assert relation_map.project_key("C:/x/mi proyecto (copia)") == "mi_proyecto_copia_"


def test_remember_writes_a_readable_note_with_wikilinks(tmp_path):
    rmap = RelationMap(tmp_path / "siaw")
    rmap.remember("catalogo_tiposistema", "relation_resource", TIPO, TIPO_PATH.replace("/", "\\"))
    rmap.remember_relation("catalogo_parametrosistema", "tipo_sistema_id", "catalogo_tiposistema")

    text = (tmp_path / "siaw" / "catalogo_tiposistema.md").read_text(encoding="utf-8")
    assert "# catalogo_tiposistema" in text
    # la ruta se guarda siempre con '/', aunque se haya recibido con '\' (Windows)
    assert f"- relation_resource: [[catalogo_tiposistemaRelationResource]] · `{TIPO}` · `{TIPO_PATH}`" in text

    relations = (tmp_path / "siaw" / "catalogo_parametrosistema.md").read_text(encoding="utf-8")
    assert "- tipo_sistema_id → [[catalogo_tiposistema]]" in relations  # enlaza con la nota de la otra tabla


def test_notes_roundtrip_and_survive_reopening(tmp_path):
    folder = tmp_path / "siaw"
    model = "App\\Models\\dbsiaw\\catalogo_tiposistema"
    RelationMap(folder).remember("catalogo_tiposistema", "model", model, "app/Models/dbsiaw/catalogo_tiposistema.php")
    RelationMap(folder).remember("catalogo_tiposistema", "relation_resource", TIPO)

    # otra instancia (otra sesión): lo confirmado sigue ahí
    again = RelationMap(folder)
    note = again.get("catalogo_tiposistema")
    assert note.files["model"] == ClassRef(model, "app/Models/dbsiaw/catalogo_tiposistema.php")
    assert note.files["relation_resource"].fqcn == TIPO
    assert again.file_for("catalogo_tiposistema", "relation_resource").short == "catalogo_tiposistemaRelationResource"
    assert again.file_for("catalogo_tiposistema", "resource") is None
    assert again.get("no_existe") is None
    assert again.tables() == ["catalogo_tiposistema"]


def test_a_confirmation_replaces_the_previous_one_for_the_same_role(tmp_path):
    rmap = RelationMap(tmp_path)
    rmap.remember("t", "resource", "A\\OldResource")
    rmap.remember("t", "resource", "A\\NewResource")
    assert rmap.file_for("t", "resource").fqcn == "A\\NewResource"


def test_forget_removes_the_role_and_the_note_when_empty(tmp_path):
    rmap = RelationMap(tmp_path)
    rmap.remember("t", "resource", "A\\R")
    rmap.remember("t", "model", "A\\M")
    rmap.forget("t", "resource")
    assert rmap.file_for("t", "resource") is None and rmap.file_for("t", "model") is not None
    rmap.forget("t", "model")
    assert rmap.get("t") is None and rmap.tables() == []


def test_unknown_role_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        RelationMap(tmp_path).remember("t", "controller", "A\\C")


def test_hand_edited_notes_still_parse():
    text = (
        "# t\n\nTexto libre que se ignora.\n\n## Archivos\n"
        "- model: [[M]] · `A\\M`\n"
        "- resource: [[R]] · `A\\R` · `app/R.php`\n"
        "- controller: [[C]] · `A\\C`\n"  # rol que el mapa no guarda: se ignora
        "linea suelta\n\n## Relaciones\n- x_id → [[otra]]\n"
    )
    note = relation_map.parse_note("t", text)
    assert set(note.files) == {"model", "resource"}
    assert note.files["model"].path == "" and note.files["resource"].path == "app/R.php"
    assert note.relations == {"x_id": "otra"}


def test_layout_note_roundtrip(tmp_path):
    custom = STANDARD_LAYOUT.with_placement(
        "store_request", RolePlacement("app/Http/Request/dbsiaw/{table}", "Store{table}Request"), layout.ORIGIN_PROJECT
    ).with_placement(
        "service", RolePlacement("src/Svc/{Prefijo}", "{Modulo}Service", "Acme\\Svc\\{Prefijo}"), layout.ORIGIN_MANUAL
    )
    rmap = RelationMap(tmp_path)
    assert rmap.load_layout() is None
    rmap.save_layout(custom, relation_map.DECISION_PROJECT)

    loaded, decision = RelationMap(tmp_path).load_layout()
    assert decision == "proyecto"
    assert loaded.placements == custom.placements
    assert loaded.origin("store_request") == "proyecto" and loaded.origin("service") == "manual"
    assert loaded.placement("service").namespace == "Acme\\Svc\\{Prefijo}"
    assert "tiny_resource" in (tmp_path / "_estructura.md").read_text(encoding="utf-8")
    assert rmap.tables() == []  # la nota de estructura no cuenta como una tabla


def test_export_and_import_move_the_map_to_another_machine(tmp_path):
    origin = RelationMap(tmp_path / "pc1")
    origin.remember("catalogo_tiposistema", "relation_resource", TIPO, "app/x.php")
    origin.remember_relation("catalogo_parametrosistema", "tipo_sistema_id", "catalogo_tiposistema")
    origin.save_layout(STANDARD_LAYOUT, relation_map.DECISION_STANDARD)

    vault = tmp_path / "vault"
    assert origin.export_to(vault) == 3  # 2 tablas + la estructura
    assert (vault / "catalogo_tiposistema.md").exists()

    other = RelationMap(tmp_path / "pc2")
    assert other.import_from(vault) == 2
    assert other.file_for("catalogo_tiposistema", "relation_resource").fqcn == TIPO
    assert other.get("catalogo_parametrosistema").relations == {"tipo_sistema_id": "catalogo_tiposistema"}
    assert other.load_layout() is not None


def test_import_merges_and_the_imported_note_wins_on_conflict(tmp_path):
    mine = RelationMap(tmp_path / "mine")
    mine.remember("t", "resource", "A\\Old")
    mine.remember("t", "model", "A\\M")
    theirs = RelationMap(tmp_path / "theirs")
    theirs.remember("t", "resource", "A\\New")

    mine.import_from(tmp_path / "theirs")
    assert mine.file_for("t", "resource").fqcn == "A\\New"
    assert mine.file_for("t", "model").fqcn == "A\\M"  # lo que no chocó se conserva


def test_import_does_not_overwrite_an_existing_layout_decision(tmp_path):
    mine = RelationMap(tmp_path / "mine")
    mine.save_layout(STANDARD_LAYOUT, relation_map.DECISION_STANDARD)
    theirs = RelationMap(tmp_path / "theirs")
    theirs.save_layout(
        STANDARD_LAYOUT.with_placement("service", RolePlacement("x", "{table}S"), layout.ORIGIN_MANUAL),
        relation_map.DECISION_CUSTOM,
    )

    mine.import_from(tmp_path / "theirs")
    _, decision = mine.load_layout()
    assert decision == "estandar"
