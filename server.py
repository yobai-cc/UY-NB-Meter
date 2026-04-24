from flask import Flask, request, render_template_string, redirect, url_for, make_response
import datetime

app = Flask(__name__)

HISTORY_DATA = []
MAX_HISTORY = 50

VALID_AUTH_KEYS = [
    "Basic ZWRwOk5hdmF5dWdhMTIz",
    "Basic YWRtaW46MTIzNDU2",
]

EXPECTED_BODY_LENGTH = 158

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>HMWSSB API Request Log</title>
    <meta http-equiv="refresh" content="8">
    <style>
        body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; background: #f4f6f8; color: #222; }
        .container { max-width: 96%; margin: 20px auto; }
        .header { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px; padding: 16px 20px; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
        .header h1 { margin: 0; font-size: 22px; }
        .header .meta { font-size: 12px; color: #666; margin-top: 4px; }
        .actions a { color: #c62828; text-decoration: none; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
        th, td { border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; vertical-align: top; font-size: 12px; }
        th { background: #1f2937; color: #fff; white-space: nowrap; }
        tr.success { background: #f0fff4; }
        tr.fail { background: #fff5f5; }
        .mono { font-family: Consolas, Monaco, monospace; word-break: break-all; white-space: pre-wrap; }
        .status-ok { color: #1b5e20; font-weight: bold; }
        .status-fail { color: #b71c1c; font-weight: bold; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1>HMWSSB API Request Log</h1>
            <div class="meta">Endpoint: /HMWSSBAPI/PostMeterReadingData | Accept rule: decoded hex payload length must equal 158 bytes</div>
        </div>
        <div class="actions">
            <a href="/clear">Clear History</a>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Result</th>
                <th>Auth</th>
                <th>Raw Body Text Length</th>
                <th>Hex Text Length</th>
                <th>Protocol Byte Length</th>
                <th>Field Count</th>
                <th>Decode Status</th>
                <th>Error</th>
                <th>Raw Data</th>
            </tr>
        </thead>
        <tbody>
            {% for item in data %}
            <tr class="{{ 'success' if item.Success else 'fail' }}">
                <td>{{ item.Time }}</td>
                <td>
                    {% if item.Success %}
                        <span class="status-ok">200 OK</span>
                    {% else %}
                        <span class="status-fail">{{ '401 faile' if not item.AuthPassed else '400 faile' }}</span>
                    {% endif %}
                </td>
                <td>{{ item.AuthDisplay }}</td>
                <td>{{ item.RawBodyTextLength }}</td>
                <td>{{ item.HexTextLength }}</td>
                <td>{{ item.ProtocolByteLength }}</td>
                <td>{{ item.FieldCount }}</td>
                <td>{{ item.HexDecodeStatus }}</td>
                <td>{{ item.ErrorType }}{% if item.ErrorMsg %}: {{ item.ErrorMsg }}{% endif %}</td>
                <td class="mono">{{ item.RawData }}</td>
            </tr>
            {% endfor %}
            {% if not data %}
            <tr>
                <td colspan="10">No requests recorded.</td>
            </tr>
            {% endif %}
        </tbody>
    </table>
</div>
</body>
</html>
"""


def record_entry(
    success,
    raw_data,
    auth_header,
    auth_passed,
    length_passed,
    raw_body_text_length,
    hex_text_length,
    protocol_byte_length,
    field_count,
    hex_decode_status,
    error_type="",
    error_msg="",
):
    entry = {
        "Pkey": len(HISTORY_DATA) + 1,
        "Time": datetime.datetime.now().isoformat(timespec="seconds"),
        "Success": success,
        "AuthPassed": auth_passed,
        "LengthPassed": length_passed,
        "RawBodyTextLength": raw_body_text_length,
        "HexTextLength": hex_text_length,
        "ProtocolByteLength": protocol_byte_length,
        "FieldCount": field_count,
        "HexDecodeStatus": hex_decode_status,
        "RawData": raw_data,
        "ErrorType": error_type,
        "ErrorMsg": error_msg,
        "AuthHeader": auth_header or "",
    }

    if not auth_header:
        entry["AuthDisplay"] = "PASS (missing)"
    elif auth_passed:
        entry["AuthDisplay"] = "PASS"
    else:
        entry["AuthDisplay"] = "FAIL"

    HISTORY_DATA.append(entry)
    if len(HISTORY_DATA) > MAX_HISTORY:
        HISTORY_DATA.pop(0)


def plain_text_response(body, status_code):
    response = make_response(body, status_code)
    response.mimetype = "text/plain"
    return response


@app.route('/')
def index():
    display_data = sorted(HISTORY_DATA, key=lambda item: item["Pkey"], reverse=True)
    return render_template_string(HTML_TEMPLATE, data=display_data)


@app.route('/clear')
def clear_history():
    global HISTORY_DATA
    HISTORY_DATA = []
    return redirect(url_for('index'))


@app.route('/HMWSSBAPI/PostMeterReadingData', methods=['POST'])
def post_reading():
    raw_bytes = request.get_data(cache=True)
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    raw_body_text_length = len(raw_bytes)
    field_count = len(raw_text.split(',')) if raw_text else 0

    stripped_text = raw_text.strip()
    hex_text = "".join(stripped_text.split())
    hex_text_length = len(hex_text)
    protocol_byte_length = 0
    hex_decode_status = "Empty"
    error_type = ""
    error_msg = ""

    if not hex_text:
        error_type = "Empty Body"
        error_msg = "Request body is empty after trimming whitespace"
    elif not all(c in "0123456789abcdefABCDEF" for c in hex_text):
        hex_decode_status = "Not hex text"
        error_type = "Not Hex Text"
        error_msg = "Request body contains non-hex characters after trimming whitespace"
    elif hex_text_length % 2 != 0:
        hex_decode_status = "Odd length"
        error_type = "Odd Hex Length"
        error_msg = "Hex text length must be even"
    else:
        try:
            payload = bytes.fromhex(hex_text)
            protocol_byte_length = len(payload)
            hex_decode_status = "OK"
        except ValueError:
            hex_decode_status = "Decode failed"
            error_type = "Hex Decode Failed"
            error_msg = "Request body could not be decoded as hex"

    auth_header = request.headers.get("Authorization")
    auth_passed = (auth_header is None) or (auth_header in VALID_AUTH_KEYS)
    length_passed = hex_decode_status == "OK" and protocol_byte_length == EXPECTED_BODY_LENGTH

    if not auth_passed:
        record_entry(
            success=False,
            raw_data=raw_text,
            auth_header=auth_header,
            auth_passed=False,
            length_passed=length_passed,
            raw_body_text_length=raw_body_text_length,
            hex_text_length=hex_text_length,
            protocol_byte_length=protocol_byte_length,
            field_count=field_count,
            hex_decode_status=hex_decode_status,
            error_type="Auth Failed",
            error_msg="Authorization header is not in VALID_AUTH_KEYS",
        )
        return plain_text_response("faile", 401)

    if not length_passed:
        if not error_type:
            error_type = "Protocol Length Failed"
            error_msg = f"Decoded hex payload length must be {EXPECTED_BODY_LENGTH} bytes"

        record_entry(
            success=False,
            raw_data=raw_text,
            auth_header=auth_header,
            auth_passed=True,
            length_passed=False,
            raw_body_text_length=raw_body_text_length,
            hex_text_length=hex_text_length,
            protocol_byte_length=protocol_byte_length,
            field_count=field_count,
            hex_decode_status=hex_decode_status,
            error_type=error_type,
            error_msg=error_msg,
        )
        return plain_text_response("faile", 400)

    record_entry(
        success=True,
        raw_data=raw_text,
        auth_header=auth_header,
        auth_passed=True,
        length_passed=True,
        raw_body_text_length=raw_body_text_length,
        hex_text_length=hex_text_length,
        protocol_byte_length=protocol_byte_length,
        field_count=field_count,
        hex_decode_status=hex_decode_status,
    )
    return plain_text_response("OK", 200)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=15556)
