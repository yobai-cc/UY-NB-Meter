from flask import Flask, request, render_template_string, redirect, url_for, make_response, jsonify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
import datetime
import os

app = Flask(__name__)

HISTORY_DATA = []
MAX_HISTORY = 50

VALID_AUTH_KEYS = [
    "Basic ZWRwOk5hdmF5dWdhMTIz",
    "Basic YWRtaW46MTIzNDU2",
]

EXPECTED_BODY_LENGTH = 158
APP_VERSION = "v2026.04.27-aesgcm"
DEFAULT_AES_GCM_KEY_HEX = "b8286d10dc8ae670189223a299b0affb"
DEFAULT_AES_GCM_RESPONSE_KEY_HEX = "45e036e26c95279ee61c8f452ee35543"
DEFAULT_AES_GCM_KEY = bytes.fromhex(DEFAULT_AES_GCM_KEY_HEX)
DEFAULT_AES_GCM_RESPONSE_KEY = bytes.fromhex(DEFAULT_AES_GCM_RESPONSE_KEY_HEX)


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_bytes_env(name):
    value = os.getenv(name)
    if value is None or value == "":
        return None
    if value.startswith("hex:"):
        return bytes.fromhex(value[4:])
    if value.startswith("base64:"):
        return base64.b64decode(value[7:])
    if value.startswith("text:"):
        return value[5:].encode("utf-8")
    return value.encode("utf-8")


app.config.setdefault("AES_GCM_ENABLED", env_flag("AES_GCM_ENABLED", False))
app.config.setdefault("AES_GCM_KEY", load_bytes_env("AES_GCM_KEY") or DEFAULT_AES_GCM_KEY)
app.config.setdefault(
    "AES_GCM_RESPONSE_KEY",
    load_bytes_env("AES_GCM_RESPONSE_KEY") or DEFAULT_AES_GCM_RESPONSE_KEY,
)
app.config.setdefault("AES_GCM_REQUEST_AAD", load_bytes_env("AES_GCM_REQUEST_AAD"))
app.config.setdefault("AES_GCM_RESPONSE_AAD", load_bytes_env("AES_GCM_RESPONSE_AAD"))
app.config.setdefault("AES_GCM_KEY_STORE_PATH", os.getenv("AES_GCM_KEY_STORE_PATH"))
app.config.setdefault("AES_GCM_ACTIVE_KEY_NAME", os.getenv("AES_GCM_ACTIVE_KEY_NAME", "default"))


def aes_gcm_enabled():
    return bool(app.config.get("AES_GCM_ENABLED"))


def auth_passed_for_header(auth_header):
    return (auth_header is None) or (auth_header in VALID_AUTH_KEYS)


def current_key_hex(kind="request"):
    key = app.config.get("AES_GCM_KEY") if kind == "request" else app.config.get("AES_GCM_RESPONSE_KEY")
    return key.hex() if key else ""


def key_source(kind="request"):
    env_name = "AES_GCM_KEY" if kind == "request" else "AES_GCM_RESPONSE_KEY"
    if os.getenv(env_name):
        return env_name
    return "built-in test key"


def get_key_store_path():
    return app.config.get("AES_GCM_KEY_STORE_PATH")


def load_key_store():
    path = get_key_store_path()
    if not path or not os.path.exists(path):
        return {"active_key_name": app.config.get("AES_GCM_ACTIVE_KEY_NAME", "default"), "keys": {}}

    with open(path, "r", encoding="utf-8") as fh:
        data = fh.read().strip()
    if not data:
        return {"active_key_name": app.config.get("AES_GCM_ACTIVE_KEY_NAME", "default"), "keys": {}}

    import json
    payload = json.loads(data)
    payload.setdefault("active_key_name", app.config.get("AES_GCM_ACTIVE_KEY_NAME", "default"))
    payload.setdefault("keys", {})
    return payload


def save_key_store(store):
    path = get_key_store_path()
    if not path:
        raise ValueError("AES_GCM_KEY_STORE_PATH is not configured")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import json
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)


def generate_key_record(name):
    key_hex = os.urandom(16).hex()
    store = load_key_store()
    store.setdefault("keys", {})[name] = {
        "key_hex": key_hex,
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    store["active_key_name"] = name
    save_key_store(store)
    app.config["AES_GCM_ACTIVE_KEY_NAME"] = name
    app.config["AES_GCM_KEY"] = bytes.fromhex(key_hex)
    app.config["AES_GCM_RESPONSE_KEY"] = bytes.fromhex(key_hex)
    return {"name": name, "key_hex": key_hex, "key_length": 16}


def activate_key_record(name):
    store = load_key_store()
    record = store.get("keys", {}).get(name)
    if not record:
        raise KeyError(name)
    key_hex = record["key_hex"]
    store["active_key_name"] = name
    save_key_store(store)
    app.config["AES_GCM_ACTIVE_KEY_NAME"] = name
    app.config["AES_GCM_KEY"] = bytes.fromhex(key_hex)
    app.config["AES_GCM_RESPONSE_KEY"] = bytes.fromhex(key_hex)
    return {"active_key_name": name, "key_hex": key_hex}


def get_key_management_info():
    store = load_key_store()
    return {
        "aes_enabled": aes_gcm_enabled(),
        "active_key_name": store.get("active_key_name") or app.config.get("AES_GCM_ACTIVE_KEY_NAME"),
        "key_names": sorted(store.get("keys", {}).keys()),
        "key_store_path": get_key_store_path(),
        "request_key_hex": current_key_hex("request"),
        "response_key_hex": current_key_hex("response"),
        "request_key_source": key_source("request"),
        "response_key_source": key_source("response"),
        "expected_body_length": EXPECTED_BODY_LENGTH,
        "valid_auth_keys": VALID_AUTH_KEYS,
    }


def get_aes_gcm_key(kind="request"):
    key = app.config.get("AES_GCM_KEY") if kind == "request" else app.config.get("AES_GCM_RESPONSE_KEY")
    if not key or len(key) != 16:
        raise ValueError("AES-128-GCM key must be exactly 16 bytes")
    return key


def get_aes_gcm_aad(kind="request"):
    return app.config.get("AES_GCM_REQUEST_AAD") if kind == "request" else app.config.get("AES_GCM_RESPONSE_AAD")


def decrypt_request_body(encoded_text):
    decoded = base64.b64decode(encoded_text, validate=True)
    if len(decoded) < 12 + 16:
        raise ValueError("AES-128-GCM payload must contain nonce+ciphertext+tag")
    nonce = decoded[:12]
    payload = decoded[12:]
    plaintext = AESGCM(get_aes_gcm_key("request")).decrypt(nonce, payload, get_aes_gcm_aad("request"))
    return plaintext.decode("utf-8")


def encrypt_response_body(plain_text):
    nonce = os.urandom(12)
    payload = AESGCM(get_aes_gcm_key("response")).encrypt(
        nonce,
        plain_text.encode("utf-8"),
        get_aes_gcm_aad("response"),
    )
    return base64.b64encode(nonce + payload).decode("ascii")

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
        .version-badge { display: inline-block; margin-top: 8px; padding: 4px 10px; border-radius: 999px; background: #c62828; color: #fff; font-size: 13px; font-weight: bold; letter-spacing: 0.3px; }
        .actions a { color: #c62828; text-decoration: none; font-size: 13px; }
        .panel { margin-bottom: 16px; padding: 16px 20px; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
        .panel h2 { margin: 0 0 12px; font-size: 18px; }
        .panel-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .panel-item { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 12px; }
        .panel-label { display: block; font-size: 12px; color: #666; margin-bottom: 4px; }
        .panel-value { font-family: Consolas, Monaco, monospace; font-size: 13px; word-break: break-all; }
        .guide { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
        .guide-block { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px 14px; }
        .guide-block h3 { margin: 0 0 8px; font-size: 14px; }
        .guide-block ul { margin: 0; padding-left: 18px; }
        .guide-block li { margin: 4px 0; font-size: 13px; }
        code { font-family: Consolas, Monaco, monospace; background: #eef2f7; border-radius: 4px; padding: 1px 4px; }
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
            <div class="meta">Endpoint: /HMWSSBAPI/PostMeterReadingData | Request: AES-128-GCM decrypt | Response: AES-128-GCM encrypt | Accept rule: decoded hex payload length must equal 158 bytes</div>
            <div class="version-badge">Version {{ version }}</div>
        </div>
        <div class="actions">
            <a href="/clear">Clear History</a>
        </div>
    </div>

    <div class="panel">
        <h2>Key Management</h2>
        <div class="panel-grid">
            <div class="panel-item">
                <span class="panel-label">AES-GCM Mode</span>
                <span class="panel-value">{{ 'Enabled' if key_info.aes_enabled else 'Disabled (plaintext mode)' }}</span>
            </div>
            <div class="panel-item">
                <span class="panel-label">Active Key</span>
                <span class="panel-value">{{ key_info.active_key_name or 'None' }}</span>
            </div>
            <div class="panel-item">
                <span class="panel-label">Stored Keys</span>
                <span class="panel-value">{{ key_info.key_names | join(', ') if key_info.key_names else 'None' }}</span>
            </div>
            <div class="panel-item">
                <span class="panel-label">Key Store Path</span>
                <span class="panel-value">{{ key_info.key_store_path or 'Not configured' }}</span>
            </div>
            <div class="panel-item">
                <span class="panel-label">Generate AES-128 Key</span>
                <span class="panel-value">POST /keys/generate</span>
            </div>
            <div class="panel-item">
                <span class="panel-label">Request AES-128 Key</span>
                <span class="panel-value">{{ key_info.request_key_hex }} ({{ key_info.request_key_source }})</span>
            </div>
            <div class="panel-item">
                <span class="panel-label">Response AES-128 Key</span>
                <span class="panel-value">{{ key_info.response_key_hex }} ({{ key_info.response_key_source }})</span>
            </div>
        </div>
    </div>

    <div class="panel">
        <h2>Test Usage Guide</h2>
        <div class="guide">
            <div class="guide-block">
                <h3>Protocol</h3>
                <ul>
                    <li>POST path: <code>/HMWSSBAPI/PostMeterReadingData</code></li>
                    <li>Encrypted request format: <code>base64(12-byte nonce + AES-GCM ciphertext + 16-byte tag)</code></li>
                    <li>Decrypted request body must be hex text, for example <code>AA</code> repeated {{ key_info.expected_body_length }} times.</li>
                    <li>Decoded protocol payload length must equal <code>{{ key_info.expected_body_length }}</code> bytes.</li>
                    <li>Success response is <code>OK</code>; failure response is <code>faile</code>. When AES mode is enabled, responses are AES-GCM encrypted.</li>
                </ul>
            </div>
            <div class="guide-block">
                <h3>Authorization</h3>
                <ul>
                    <li>No <code>Authorization</code> header: accepted for development testing.</li>
                    <li>With <code>Authorization</code>: value must match the whitelist.</li>
                    <li>Whitelist: <code>{{ key_info.valid_auth_keys | join(' / ') }}</code></li>
                    <li>Key APIs use the same rule: missing Authorization is accepted; invalid Authorization is rejected.</li>
                </ul>
            </div>
            <div class="guide-block">
                <h3>Failure Reason Map</h3>
                <ul>
                    <li><code>Auth Failed</code>: Authorization header was provided but is not whitelisted.</li>
                    <li><code>Decrypt Failed</code>: request is not valid base64, key/tag is wrong, or AES payload is malformed.</li>
                    <li><code>Not Hex Text</code>: decrypted text contains non-hex characters.</li>
                    <li><code>Odd Hex Length</code>: decrypted hex text has an odd number of characters.</li>
                    <li><code>Protocol Length Failed</code>: hex decoded successfully but byte length is not {{ key_info.expected_body_length }}.</li>
                </ul>
            </div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Result</th>
                <th>Auth</th>
                <th>Raw Body Text Length</th>
                <th>Decrypted Text Length</th>
                <th>Hex Text Length</th>
                <th>Protocol Byte Length</th>
                <th>Field Count</th>
                <th>Request Crypto</th>
                <th>Response Crypto</th>
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
                <td>{{ item.DecryptedTextLength }}</td>
                <td>{{ item.HexTextLength }}</td>
                <td>{{ item.ProtocolByteLength }}</td>
                <td>{{ item.FieldCount }}</td>
                <td>{{ item.RequestCryptoStatus }}</td>
                <td>{{ item.ResponseCryptoStatus }}</td>
                <td>{{ item.HexDecodeStatus }}</td>
                <td>{{ item.ErrorType }}{% if item.ErrorMsg %}: {{ item.ErrorMsg }}{% endif %}</td>
                <td class="mono">{{ item.RawData }}</td>
            </tr>
            {% endfor %}
            {% if not data %}
            <tr>
                <td colspan="13">No requests recorded.</td>
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
    decrypted_text_length,
    hex_text_length,
    protocol_byte_length,
    field_count,
    request_crypto_status,
    response_crypto_status,
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
        "DecryptedTextLength": decrypted_text_length,
        "HexTextLength": hex_text_length,
        "ProtocolByteLength": protocol_byte_length,
        "FieldCount": field_count,
        "RequestCryptoStatus": request_crypto_status,
        "ResponseCryptoStatus": response_crypto_status,
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


def response_text(plain_text, status_code):
    if not aes_gcm_enabled():
        return plain_text_response(plain_text, status_code)

    try:
        encrypted_body = encrypt_response_body(plain_text)
    except Exception:
        return plain_text_response(plain_text, status_code)
    response = make_response(encrypted_body, status_code)
    response.mimetype = "text/plain"
    return response


def key_api_auth_error():
    auth_header = request.headers.get("Authorization")
    if auth_passed_for_header(auth_header):
        return None
    return jsonify({"error": "Authorization header is not in VALID_AUTH_KEYS"}), 401


@app.route('/')
def index():
    display_data = sorted(HISTORY_DATA, key=lambda item: item["Pkey"], reverse=True)
    return render_template_string(
        HTML_TEMPLATE,
        data=display_data,
        version=APP_VERSION,
        key_info=get_key_management_info(),
    )


@app.route('/clear')
def clear_history():
    global HISTORY_DATA
    HISTORY_DATA = []
    return redirect(url_for('index'))


@app.route('/keys/generate', methods=['POST'])
def generate_key():
    auth_error = key_api_auth_error()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    record = generate_key_record(name)
    return jsonify(record)


@app.route('/keys/activate', methods=['POST'])
def activate_key():
    auth_error = key_api_auth_error()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    try:
        record = activate_key_record(name)
    except KeyError:
        return jsonify({"error": "key not found", "name": name}), 404

    return jsonify(record)


@app.route('/HMWSSBAPI/PostMeterReadingData', methods=['POST'])
def post_reading():
    raw_bytes = request.get_data(cache=True)
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    raw_body_text_length = len(raw_bytes)

    request_crypto_status = "Plaintext"
    response_crypto_status = "Plaintext"
    decrypted_text = raw_text
    error_type = ""
    error_msg = ""
    hex_decode_status = "Empty"
    protocol_byte_length = 0

    if aes_gcm_enabled():
        try:
            decrypted_text = decrypt_request_body(raw_text.strip())
            request_crypto_status = "Decrypted"
            response_crypto_status = "Encrypted"
        except Exception as exc:
            decrypted_text = ""
            request_crypto_status = "Decrypt failed"
            response_crypto_status = "Encrypted"
            error_type = "Decrypt Failed"
            error_msg = str(exc)

    decrypted_text_length = len(decrypted_text.encode("utf-8")) if decrypted_text else 0
    field_count = len(decrypted_text.split(',')) if decrypted_text else 0

    stripped_text = decrypted_text.strip()
    hex_text = "".join(stripped_text.split())
    hex_text_length = len(hex_text)

    if not error_type:
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
    auth_passed = auth_passed_for_header(auth_header)
    length_passed = hex_decode_status == "OK" and protocol_byte_length == EXPECTED_BODY_LENGTH

    if not auth_passed:
        record_entry(
            success=False,
            raw_data=raw_text,
            auth_header=auth_header,
            auth_passed=False,
            length_passed=length_passed,
            raw_body_text_length=raw_body_text_length,
            decrypted_text_length=decrypted_text_length,
            hex_text_length=hex_text_length,
            protocol_byte_length=protocol_byte_length,
            field_count=field_count,
            request_crypto_status=request_crypto_status,
            response_crypto_status=response_crypto_status,
            hex_decode_status=hex_decode_status,
            error_type="Auth Failed",
            error_msg="Authorization header is not in VALID_AUTH_KEYS",
        )
        return response_text("faile", 401)

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
            decrypted_text_length=decrypted_text_length,
            hex_text_length=hex_text_length,
            protocol_byte_length=protocol_byte_length,
            field_count=field_count,
            request_crypto_status=request_crypto_status,
            response_crypto_status=response_crypto_status,
            hex_decode_status=hex_decode_status,
            error_type=error_type,
            error_msg=error_msg,
        )
        return response_text("faile", 400)

    record_entry(
        success=True,
        raw_data=raw_text,
        auth_header=auth_header,
        auth_passed=True,
        length_passed=True,
        raw_body_text_length=raw_body_text_length,
        decrypted_text_length=decrypted_text_length,
        hex_text_length=hex_text_length,
        protocol_byte_length=protocol_byte_length,
        field_count=field_count,
        request_crypto_status=request_crypto_status,
        response_crypto_status=response_crypto_status,
        hex_decode_status=hex_decode_status,
    )
    return response_text("OK", 200)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=15556)
