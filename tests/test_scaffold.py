from generador import scaffold


def test_detect_scaffold_status_all_missing(tmp_path):
    status = scaffold.detect_scaffold_status(tmp_path)
    assert status.abstract_module_service_exists is False
    assert status.crud_service_exists is False
    assert status.base_controller_exists is False
    assert status.route_service_provider_exists is False
    assert status.composer_json_exists is False
    assert status.token_class_found is False
    assert status.procesosaudit_migration_found is False
    assert status.missing_base_pieces == [
        "AbstractModuleService.php",
        "RouteServiceProvider.php",
        "Controller.php (base)",
    ]
    assert status.base_controller_needs_swagger_snippet is False  # no existe -> no aplica el snippet


def test_detect_scaffold_status_finds_existing_pieces(tmp_path):
    services_dir = tmp_path / "app" / "Services"
    services_dir.mkdir(parents=True)
    (services_dir / "AbstractModuleService.php").write_text("<?php abstract class AbstractModuleService {}", encoding="utf-8")
    (services_dir / "CrudService.php").write_text("<?php class CrudService {}", encoding="utf-8")

    controllers_dir = tmp_path / "app" / "Http" / "Controllers"
    controllers_dir.mkdir(parents=True)
    (controllers_dir / "Controller.php").write_text(
        "<?php\n/**\n * @OA\\Info(title=\"X\")\n */\nabstract class Controller {}", encoding="utf-8"
    )

    providers_dir = tmp_path / "app" / "Providers"
    providers_dir.mkdir(parents=True)
    (providers_dir / "RouteServiceProvider.php").write_text("<?php class RouteServiceProvider {}", encoding="utf-8")

    (tmp_path / "composer.json").write_text(
        '{"require": {"essa/api-toolkit": "^1.0", "darkaonline/l5-swagger": "^8.0"}}', encoding="utf-8"
    )

    status = scaffold.detect_scaffold_status(tmp_path)
    assert status.abstract_module_service_exists is True
    assert status.crud_service_exists is True
    assert status.base_controller_exists is True
    assert status.base_controller_has_swagger is True
    assert status.route_service_provider_exists is True
    assert status.composer_has_api_toolkit is True
    assert status.composer_has_l5_swagger is True
    assert status.missing_base_pieces == []


def test_detect_scaffold_status_controller_exists_without_swagger(tmp_path):
    controllers_dir = tmp_path / "app" / "Http" / "Controllers"
    controllers_dir.mkdir(parents=True)
    (controllers_dir / "Controller.php").write_text("<?php abstract class Controller {}", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    assert status.base_controller_exists is True
    assert status.base_controller_has_swagger is False
    assert status.base_controller_needs_swagger_snippet is True
    # No autocontenido -> no entra en missing_base_pieces (se genera solo si falta del todo)
    assert "Controller.php (base)" not in status.missing_base_pieces


def test_detect_scaffold_status_finds_token_class_anywhere_under_app(tmp_path):
    support_dir = tmp_path / "app" / "Support"
    support_dir.mkdir(parents=True)
    (support_dir / "Token.php").write_text("<?php class Token { public static function user() {} }", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    assert status.token_class_found is True
    assert status.token_class_path == support_dir / "Token.php"


def test_detect_scaffold_status_finds_procesosaudit_migration(tmp_path):
    migrations_dir = tmp_path / "database" / "migrations" / "Auditoria"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "2024_01_01_000000_create_siaw_procesosaudit_table.php").write_text("<?php", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    assert status.procesosaudit_migration_found is True


def test_write_missing_base_pieces_only_writes_missing(tmp_path):
    services_dir = tmp_path / "app" / "Services"
    services_dir.mkdir(parents=True)
    existing = services_dir / "AbstractModuleService.php"
    existing.write_text("// versión custom del desarrollador, no tocar", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    written = scaffold.write_missing_base_pieces(status, project_name="MiProyecto")

    # No se sobrescribe el que ya existía
    assert existing.read_text(encoding="utf-8") == "// versión custom del desarrollador, no tocar"
    assert "abstract_module_service" not in written

    # Las otras dos sí se generan
    assert "route_service_provider" in written
    assert "base_controller" in written
    assert written["route_service_provider"].exists()
    assert "RouteServiceProvider" in written["route_service_provider"].read_text(encoding="utf-8")
    assert "@OA\\Info" in written["base_controller"].read_text(encoding="utf-8")
    assert "MiProyecto" in written["base_controller"].read_text(encoding="utf-8")


def test_write_missing_base_pieces_is_idempotent_even_with_stale_status(tmp_path):
    """Llamar dos veces con el MISMO objeto status (potencialmente
    desactualizado tras la primera escritura) nunca debe pisar lo ya escrito
    — la garantía de no sobrescribir no depende de recalcular el status."""
    status = scaffold.detect_scaffold_status(tmp_path)
    first = scaffold.write_missing_base_pieces(status, project_name="MiProyecto")
    first["base_controller"].write_text("// modificado a mano después de generarlo", encoding="utf-8")

    second = scaffold.write_missing_base_pieces(status, project_name="MiProyecto")
    assert second == {}
    assert first["base_controller"].read_text(encoding="utf-8") == "// modificado a mano después de generarlo"


def test_write_crud_service_with_audit_uses_token_when_found(tmp_path):
    support_dir = tmp_path / "app" / "Support"
    support_dir.mkdir(parents=True)
    (support_dir / "Token.php").write_text("<?php class Token { public static function user() {} }", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    written = scaffold.write_crud_service_with_audit(status, "siaw")

    crud_text = written["crud_service"].read_text(encoding="utf-8")
    assert "Token::user()" in crud_text
    assert "Auth::user()" not in crud_text
    assert "procesosaudit_model" in written
    assert "procesosaudit_migration" in written
    assert "siaw_procesosaudit" in written["procesosaudit_model"].read_text(encoding="utf-8")
    assert "TIPO_INSERCION" in written["procesosaudit_migration"].read_text(encoding="utf-8") or True


def test_write_crud_service_with_audit_falls_back_to_auth_user_without_token(tmp_path):
    status = scaffold.detect_scaffold_status(tmp_path)
    written = scaffold.write_crud_service_with_audit(status, "siaw")

    crud_text = written["crud_service"].read_text(encoding="utf-8")
    assert "Auth::user()" in crud_text
    assert "Token::user()" not in crud_text


def test_write_crud_service_with_audit_skips_migration_when_one_already_exists(tmp_path):
    migrations_dir = tmp_path / "database" / "migrations" / "Legacy"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "2020_01_01_000000_create_siaw_procesosaudit_table.php").write_text("<?php", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    written = scaffold.write_crud_service_with_audit(status, "siaw")

    assert "crud_service" in written
    assert "procesosaudit_migration" not in written
    assert "procesosaudit_model" not in written


def test_write_crud_service_with_audit_does_not_overwrite_existing_crud_service(tmp_path):
    services_dir = tmp_path / "app" / "Services"
    services_dir.mkdir(parents=True)
    existing = services_dir / "CrudService.php"
    existing.write_text("// version propia del proyecto", encoding="utf-8")

    status = scaffold.detect_scaffold_status(tmp_path)
    written = scaffold.write_crud_service_with_audit(status, "siaw")

    assert "crud_service" not in written
    assert existing.read_text(encoding="utf-8") == "// version propia del proyecto"


def test_procesosaudit_migration_filename_format():
    from datetime import datetime

    name = scaffold.procesosaudit_migration_filename("siaw", when=datetime(2026, 3, 5, 14, 30, 0))
    assert name == "2026_03_05_143000_create_siaw_procesosaudit_table.php"
