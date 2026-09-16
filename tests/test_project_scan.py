from generador.project_scan import scan_backend_project, suggested_loader_snippet


def test_scan_unknown_root(tmp_path):
    result = scan_backend_project(tmp_path)
    assert result.laravel_version_hint == "desconocido"
    assert result.provider_file_checked is None
    assert any("raíz correcta" in w for w in result.warnings)


def test_scan_laravel11_with_loader_registered(tmp_path):
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "app.php").write_text(
        "return Application::configure()->withRouting(then: function () {\n"
        "    foreach (glob(base_path('routes/modules/*.php')) as $f) { require $f; }\n"
        "});\n",
        encoding="utf-8",
    )

    result = scan_backend_project(tmp_path)
    assert result.laravel_version_hint == "L11+"
    assert result.modules_loader_registered is True
    assert result.warnings == []


def test_scan_laravel10_without_loader(tmp_path):
    provider_dir = tmp_path / "app" / "Providers"
    provider_dir.mkdir(parents=True)
    (provider_dir / "RouteServiceProvider.php").write_text(
        "<?php class RouteServiceProvider extends ServiceProvider { public function boot() {} }",
        encoding="utf-8",
    )

    result = scan_backend_project(tmp_path)
    assert result.laravel_version_hint == "L10-"
    assert result.modules_loader_registered is False
    assert any("routes/modules/*.php" in w for w in result.warnings)


def test_scan_detects_existing_module_routes(tmp_path):
    routes_modules = tmp_path / "routes" / "modules"
    routes_modules.mkdir(parents=True)
    (routes_modules / "usuarios.php").write_text("<?php", encoding="utf-8")
    (routes_modules / "roles.php").write_text("<?php", encoding="utf-8")

    result = scan_backend_project(tmp_path)
    assert result.routes_modules_dir_exists is True
    assert result.existing_module_routes == ["roles.php", "usuarios.php"]


def test_suggested_snippet_varies_by_version():
    l11_snippet = suggested_loader_snippet("L11+")
    l10_snippet = suggested_loader_snippet("L10-")
    assert "bootstrap/app.php" in l11_snippet
    assert "RouteServiceProvider.php" in l10_snippet
    assert "routes/modules" in l11_snippet
    assert "routes/modules" in l10_snippet
