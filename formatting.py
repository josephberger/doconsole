def format_table(headers, results=None, preamble=None, footer=None):
    def calculate_max_widths():
        max_widths = {}
        for header, key in headers.items():
            header_width = len(str(header))
            value_width = max(len(str(r[key])) for r in results)
            max_widths[header] = max(header_width, value_width)
        return max_widths

    def create_format_string(max_widths):
        spacing = 2
        return " ".join(f"{{:<{width+spacing}}}" for width in max_widths.values())

    def format_header(format_string):
        return format_string.format(*headers.keys())

    def format_data(format_string):
        data_strs = []
        for r in results:
            result_values = [r[key] for key in headers.values()]
            data_strs.append(format_string.format(*result_values))
        return "\n".join(data_strs)

    output = ""

    if preamble:
        output += preamble + "\n\n"

    if results:
        max_widths = calculate_max_widths()
        format_string = create_format_string(max_widths)

        header_str = format_header(format_string)
        data_str = format_data(format_string)

        output += header_str + "\n" + data_str

    if footer:
        if results:
            output += "\n\n"
        output += "\n".join(footer)

    return output + "\n"


def format_single_dict(data, preamble=None, footer=None):
    def calculate_max_widths():
        return max(len(str(key)) for key in data.keys())

    def format_data(max_key_width):
        spacing = 2
        lines = []
        for key, value in data.items():
            lines.append(f"{key:<{max_key_width + spacing}}{value}")
        return "\n".join(lines)

    output = ""

    if preamble:
        output += preamble + "\n\n"

    max_key_width = calculate_max_widths()
    data_str = format_data(max_key_width)

    output += data_str

    if footer:
        output += "\n\n" + "\n".join(footer)

    return output + "\n"


def format_list_into_columns(data, num_columns=None, auto=True):
    if auto:
        if num_columns is not None:
            raise ValueError("Auto mode is enabled, num_columns argument should not be provided")

        total_items = len(data)

        if total_items <= 40:
            num_columns = 1
        elif total_items <= 80:
            num_columns = 2
        elif total_items <= 180:
            num_columns = 3
        else:
            num_columns = 4

    if num_columns is not None and (num_columns < 1 or num_columns > 4):
        raise ValueError("Number of columns must be between 1 and 4")

    if num_columns is None:
        raise ValueError("Number of columns must be specified when auto mode is disabled")

    num_rows = (len(data) + num_columns - 1) // num_columns

    rows = [data[i * num_columns:(i + 1) * num_columns] for i in range(num_rows)]

    col_widths = [
        max(len(str(rows[row][col])) for row in range(len(rows)) if col < len(rows[row]))
        for col in range(num_columns)
    ]

    formatted_rows = []
    for row in rows:
        formatted_row = "".join(f"{str(item):<{col_widths[i] + 2}}" for i, item in enumerate(row))
        formatted_rows.append(formatted_row)

    return "\n".join(formatted_rows)
