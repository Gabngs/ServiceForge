from generador.project_scan import (
    scan_backend_project,
    scan_eloquent_connections,
    suggest_eloquent_connection,
    suggested_loader_snippet,
)


def test_scan_unknown_root(tmp_path):
    result = scan_backend_project(tmp_path)
    assert result.laravel_version_hint == "desconocido"
    assert result.provider_files_checked == []
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


def test_scan_laravel11_with_loader_in_route_service_provider(tmp_path):
    # Caso real: proyecto L11+ (bootstrap/app.php con withRouting) que igual
    # conserva un RouteServiceProvider propio -- registrado a mano en
    # bootstrap/providers.php -- con el loader de routes/modules/*.php ahí,
    # en vez de en bootstrap/app.php. Antes esto daba falso negativo porque
    # la detección de L11+ descartaba RouteServiceProvider.php de plano.
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "app.php").write_text(
        "return Application::configure()->withRouting(api: __DIR__.'/../routes/api/api.php');\n",
        encoding="utf-8",
    )
    provider_dir = tmp_path / "app" / "Providers"
    provider_dir.mkdir(parents=True)
    (provider_dir / "RouteServiceProvider.php").write_text(
        "<?php class RouteServiceProvider extends ServiceProvider {\n"
        "    public function boot(): void {\n"
        "        $files = glob(base_path('routes/modules') . DIRECTORY_SEPARATOR . '*.php') ?: [];\n"
        "        Route::prefix('api')->group(function () use ($files) { foreach ($files as $f) require $f; });\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = scan_backend_project(tmp_path)
    assert result.laravel_version_hint == "L11+"
    assert result.modules_loader_registered is True
    assert result.warnings == []
    assert len(result.provider_files_checked) == 2


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


_DATABASE_PHP = """<?php

return [
    'default' => env('DB_CONNECTION', 'mysql'),

    // 'comentada' => [ ... ],
    'connections' => [

        'sqlite' => [
            'driver' => 'sqlite',
            'url' => env('DATABASE_URL'),
            'database' => env('DB_DATABASE', database_path('database.sqlite')),
        ],

        'mysql_dbsiaw' => [
            'driver' => 'mysql',
            'options' => extension_loaded('pdo_mysql') ? array_filter([
                PDO::MYSQL_ATTR_SSL_CA => env('MYSQL_ATTR_SSL_CA'),
            ]) : [],
        ],

        "mysql_dbsip" => array(
            'driver' => 'mysql',
        ),
    ],

    'redis' => [
        'client' => 'phpredis',
        'options' => ['cluster' => 'redis'],
        'default' => ['host' => '127.0.0.1'],
        'cache' => ['database' => '1'],
    ],
];
"""


def test_scan_eloquent_connections_reads_only_the_connections_block(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.php").write_text(_DATABASE_PHP, encoding="utf-8")

    # No debe colar 'default', 'options', 'cache' (Redis) ni la clave comentada.
    assert scan_eloquent_connections(tmp_path) == ["sqlite", "mysql_dbsiaw", "mysql_dbsip"]


def test_scan_eloquent_connections_without_config_returns_empty(tmp_path):
    assert scan_eloquent_connections(tmp_path) == []


def test_scan_backend_project_exposes_eloquent_connections(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.php").write_text(_DATABASE_PHP, encoding="utf-8")
    assert scan_backend_project(tmp_path).eloquent_connections == ["sqlite", "mysql_dbsiaw", "mysql_dbsip"]


def test_suggest_eloquent_connection_matches_database_name():
    connections = ["sqlite", "mysql", "mysql_dbsiaw", "mysql_dbsip"]
    assert suggest_eloquent_connection(connections, "dbsiaw") == "mysql_dbsiaw"
    assert suggest_eloquent_connection(connections, "DBSIP") == "mysql_dbsip"
    assert suggest_eloquent_connection(connections, "mysql") == "mysql"


def test_suggest_eloquent_connection_returns_none_when_ambiguous_or_unknown():
    connections = ["mysql_a_ventas", "mysql_b_ventas"]
    assert suggest_eloquent_connection(connections, "ventas") is None  # dos candidatas
    assert suggest_eloquent_connection(connections, "otra") is None
    assert suggest_eloquent_connection(connections, "") is None
