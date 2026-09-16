from generador import mapping


def test_parse_varchar():
    parsed = mapping.parse_sql_type("varchar(100)")
    assert parsed.base == "varchar"
    assert parsed.length == 100


def test_parse_decimal():
    parsed = mapping.parse_sql_type("decimal(10,2)")
    assert parsed.base == "decimal"
    assert parsed.precision == 10
    assert parsed.scale == 2


def test_parse_enum():
    parsed = mapping.parse_sql_type("enum('activo','inactivo')")
    assert parsed.base == "enum"
    assert parsed.enum_values == ("activo", "inactivo")


def test_parse_tinyint_bool():
    parsed = mapping.parse_sql_type("tinyint(1)")
    assert parsed.base == "tinyint"
    assert parsed.length == 1


def test_validation_rules_varchar_required():
    parsed = mapping.parse_sql_type("varchar(100)")
    store, update = mapping.validation_rules(parsed, nullable=False)
    assert store == "required|string|max:100"
    assert update == "sometimes|string|max:100"


def test_validation_rules_varchar_nullable():
    parsed = mapping.parse_sql_type("varchar(100)")
    store, update = mapping.validation_rules(parsed, nullable=True)
    assert store == "nullable|string|max:100"
    assert update == "nullable|string|max:100"


def test_validation_rules_tinyint_boolean_always_sometimes():
    parsed = mapping.parse_sql_type("tinyint(1)")
    store, update = mapping.validation_rules(parsed, nullable=False)
    assert store == "sometimes|boolean"
    assert update == "sometimes|boolean"


def test_validation_rules_datetime():
    parsed = mapping.parse_sql_type("datetime")
    store, update = mapping.validation_rules(parsed, nullable=False)
    assert store == "required|date_format:Y-m-d H:i:s"
    assert update == "sometimes|date_format:Y-m-d H:i:s"


def test_validation_rules_fk_resolved():
    parsed = mapping.parse_sql_type("int")
    store, update = mapping.validation_rules(parsed, nullable=False, is_fk=True, fk_table="siaw_roles")
    assert store == "required|string|exists:siaw_roles,id"
    assert update == "sometimes|string|exists:siaw_roles,id"


def test_validation_rules_fk_resolved_nullable():
    parsed = mapping.parse_sql_type("int")
    store, update = mapping.validation_rules(parsed, nullable=True, is_fk=True, fk_table="siaw_roles")
    assert store == "nullable|string|exists:siaw_roles,id"
    assert update == "nullable|string|exists:siaw_roles,id"


def test_laravel_cast_decimal():
    parsed = mapping.parse_sql_type("decimal(10,2)")
    assert mapping.laravel_cast(parsed) == "decimal:2"


def test_laravel_cast_boolean():
    parsed = mapping.parse_sql_type("tinyint(1)")
    assert mapping.laravel_cast(parsed) == "boolean"


def test_laravel_cast_none_for_varchar():
    parsed = mapping.parse_sql_type("varchar(50)")
    assert mapping.laravel_cast(parsed) is None


def test_ts_type_fk_is_string():
    parsed = mapping.parse_sql_type("int")
    assert mapping.ts_type(parsed, is_fk=True) == "string"


def test_ts_type_boolean():
    parsed = mapping.parse_sql_type("tinyint(1)")
    assert mapping.ts_type(parsed) == "boolean"


def test_excluded_fields_frozen():
    assert "pkid" in mapping.EXCLUDED_FIELDS
    assert "created_by_id" in mapping.EXCLUDED_FIELDS
    assert "nombre" not in mapping.EXCLUDED_FIELDS
