import formatting


def test_format_table_basic():
    headers = {"Name": "name", "Age": "age"}
    rows = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    output = formatting.format_table(headers, rows)
    assert "Name" in output
    assert "Alice" in output
    assert "Bob" in output


def test_format_table_empty_results_with_footer():
    headers = {"Name": "name"}
    output = formatting.format_table(headers, [], footer=["none found"])
    assert "none found" in output


def test_format_single_dict():
    output = formatting.format_single_dict({"A": 1, "BB": 2}, preamble="Title")
    assert "Title" in output
    assert "A" in output
    assert "1" in output


def test_format_list_into_columns_single_column():
    output = formatting.format_list_into_columns(["a", "b", "c"])
    assert output.count("\n") == 2
