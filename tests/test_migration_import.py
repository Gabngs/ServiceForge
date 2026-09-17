from generador.migration_import import MigrationParseError, parse_migration

_SAMPLE = """<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{
    protected $connection = 'mysql_dbsiaw';
    protected $table = 'catalogo_premiaciones';
    public function up(): void
    {
        Schema::create($this->table, function (Blueprint $table) {
            $table->bigInteger('pkid')->autoIncrement();
            $table->string('id',36)->index()->unique();
            $table->tinyInteger('mes');
            $table->bigInteger('anio');
            $table->tinyInteger('dias')->default('0');
            $table->bigInteger('tienda_id')->index();
            $table->decimal('venta', 12, 3)->default('0');
            $table->timestamps();
            $table->softDeletes();
            $table->bigInteger('created_by_id')->nullable();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists($this->table);
    }
};
"""


def test_parse_migration_extracts_table_from_property():
    parsed = parse_migration(_SAMPLE)
    assert parsed.table == "catalogo_premiaciones"


def test_parse_migration_columns_match_describe_shape():
    parsed = parse_migration(_SAMPLE)
    by_name = {c.name: c for c in parsed.columns}

    assert by_name["pkid"].sql_type == "bigint(20)"
    assert by_name["pkid"].key == "PRI"
    assert by_name["pkid"].extra == "auto_increment"

    assert by_name["id"].sql_type == "varchar(36)"
    assert by_name["id"].key == "UNI"

    assert by_name["mes"].sql_type == "tinyint(4)"
    assert by_name["mes"].nullable is False

    assert by_name["tienda_id"].key == "MUL"
    assert by_name["dias"].default == "0"

    assert by_name["created_at"].sql_type == "timestamp"
    assert by_name["created_at"].nullable is True
    assert by_name["deleted_at"].sql_type == "timestamp"


def test_parse_migration_unique_indexes():
    parsed = parse_migration(_SAMPLE)
    assert parsed.unique_indexes == {"catalogo_premiaciones_id_unique": ["id"]}


def test_parse_migration_table_literal_and_explicit_fk():
    text = """
    Schema::create('siaw_pedidos', function (Blueprint $table) {
        $table->bigInteger('pkid')->autoIncrement();
        $table->foreignId('tienda_id')->constrained('catalogo_tienda');
        $table->foreign('cliente_id')->references('id')->on('siaw_clientes');
    });
    """
    parsed = parse_migration(text)
    assert parsed.table == "siaw_pedidos"
    assert parsed.fk_hints == {"tienda_id": "catalogo_tienda", "cliente_id": "siaw_clientes"}
    by_name = {c.name: c for c in parsed.columns}
    assert by_name["tienda_id"].sql_type == "bigint(20) unsigned"


def test_parse_migration_without_schema_create_raises():
    try:
        parse_migration("<?php // nada de nada")
        assert False, "debía levantar MigrationParseError"
    except MigrationParseError:
        pass
