import formatting


def test_print_table_basic(capsys):
    headers = {"Name": "name", "Age": "age"}
    rows = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    formatting.print_table(headers, rows)
    out = capsys.readouterr().out
    assert "Name" in out
    assert "Alice" in out
    assert "Bob" in out


def test_print_table_empty_results_with_footer(capsys):
    headers = {"Name": "name"}
    formatting.print_table(headers, [], footer=["none found"])
    out = capsys.readouterr().out
    assert "none found" in out


def test_print_table_preamble(capsys):
    formatting.print_table({"Name": "name"}, [{"name": "Alice"}], preamble="Some Title")
    out = capsys.readouterr().out
    assert "Some Title" in out


def test_print_dict(capsys):
    formatting.print_dict({"A": 1, "BB": 2}, preamble="Title")
    out = capsys.readouterr().out
    assert "Title" in out
    assert "A" in out
    assert "1" in out


def test_print_columns(capsys):
    formatting.print_columns(["alpha", "beta", "gamma"])
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "beta" in out
    assert "gamma" in out


def test_status_column_still_renders_value(capsys):
    formatting.print_table({"Status": "status"}, [{"status": "active"}, {"status": "off"}])
    out = capsys.readouterr().out
    assert "active" in out
    assert "off" in out


def test_success_error_warning_print_message(capsys):
    formatting.success("all good")
    formatting.error("something broke")
    formatting.warning("be careful")
    out = capsys.readouterr().out
    assert "all good" in out
    assert "something broke" in out
    assert "be careful" in out


def test_bracketed_content_is_not_treated_as_markup(capsys):
    formatting.error("No droplet named '[test]'.")
    out = capsys.readouterr().out
    assert "[test]" in out
