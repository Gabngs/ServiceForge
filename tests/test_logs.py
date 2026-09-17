from generador import logs


def test_build_entry_counts_files_and_lines():
    contents = {
        "model": "line1\nline2\nline3",  # 3 líneas
        "controller": "line1\nline2",  # 2 líneas
    }
    entry = logs.build_entry(
        table="siaw_usuarios",
        fk_count=1,
        field_count=4,
        elapsed_seconds=125.4,
        contents_by_key=contents,
    )
    assert entry.table == "siaw_usuarios"
    assert entry.fk_count == 1
    assert entry.field_count == 4
    assert entry.file_count == 2
    assert entry.line_count == 5
    assert entry.elapsed_seconds == 125.4
    assert entry.elapsed_minutes == 2.09
    assert entry.files == ["controller", "model"]


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "generation_log.json"
    assert logs.load_log(path) == []

    entry = logs.build_entry(
        table="siaw_usuarios", fk_count=1, field_count=4, elapsed_seconds=60.0, contents_by_key={"model": "a\nb"}
    )
    logs.append_entry(entry, path)

    loaded = logs.load_log(path)
    assert len(loaded) == 1
    assert loaded[0] == entry

    second = logs.build_entry(
        table="siaw_roles", fk_count=0, field_count=2, elapsed_seconds=30.0, contents_by_key={"model": "a"}
    )
    logs.append_entry(second, path)
    assert [e.table for e in logs.load_log(path)] == ["siaw_usuarios", "siaw_roles"]


def test_load_log_missing_or_corrupt_file_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist.json"
    assert logs.load_log(missing) == []

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("not json", encoding="utf-8")
    assert logs.load_log(corrupt) == []


def test_export_csv(tmp_path):
    entry = logs.build_entry(
        table="siaw_usuarios", fk_count=1, field_count=4, elapsed_seconds=90.0, contents_by_key={"model": "a\nb\nc"}
    )
    out = tmp_path / "log.csv"
    logs.export_csv([entry], out)

    text = out.read_text(encoding="utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0] == ",".join(logs.CSV_HEADERS)
    assert "siaw_usuarios" in lines[1]
    assert "1.5" in lines[1]  # 90s -> 1.5 min
