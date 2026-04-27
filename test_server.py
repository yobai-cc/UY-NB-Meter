import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_TEST_KEY = b"0123456789ABCDEF"
DEFAULT_TEST_NONCE = b"UYNBMETER123"
BUILTIN_REQUEST_KEY = bytes.fromhex("b8286d10dc8ae670189223a299b0affb")
BUILTIN_RESPONSE_KEY = bytes.fromhex("45e036e26c95279ee61c8f452ee35543")


MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("uynb_server", MODULE_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def build_client():
    server.app.config["TESTING"] = True
    server.HISTORY_DATA.clear()
    return server.app.test_client()


def encrypt_request(plaintext, key=DEFAULT_TEST_KEY, nonce=DEFAULT_TEST_NONCE, aad=None):
    payload = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return base64.b64encode(nonce + payload).decode("ascii")


def decrypt_response(encoded, key=DEFAULT_TEST_KEY, aad=None):
    decoded = base64.b64decode(encoded)
    nonce = decoded[:12]
    payload = decoded[12:]
    return AESGCM(key).decrypt(nonce, payload, aad).decode("utf-8")


def crypto_config(key_store_path=None):
    return {
        "AES_GCM_ENABLED": True,
        "AES_GCM_KEY": DEFAULT_TEST_KEY,
        "AES_GCM_RESPONSE_KEY": DEFAULT_TEST_KEY,
        "AES_GCM_REQUEST_AAD": None,
        "AES_GCM_RESPONSE_AAD": None,
        "AES_GCM_KEY_STORE_PATH": key_store_path,
        "AES_GCM_ACTIVE_KEY_NAME": "default",
    }


class ServerTests(unittest.TestCase):
    @mock.patch.dict(server.app.config, {
        "AES_GCM_ENABLED": True,
        "AES_GCM_KEY": BUILTIN_REQUEST_KEY,
        "AES_GCM_RESPONSE_KEY": BUILTIN_RESPONSE_KEY,
        "AES_GCM_REQUEST_AAD": None,
        "AES_GCM_RESPONSE_AAD": None,
        "AES_GCM_KEY_STORE_PATH": None,
        "AES_GCM_ACTIVE_KEY_NAME": "default",
    }, clear=False)
    def test_builtin_fixed_keys_work_for_encrypted_request_and_response(self):
        client = build_client()
        encrypted_body = encrypt_request("AA" * 158, key=BUILTIN_REQUEST_KEY)

        response = client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data=encrypted_body,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(decrypt_response(response.get_data(as_text=True), key=BUILTIN_RESPONSE_KEY), "OK")

    @mock.patch.dict(server.app.config, crypto_config(), clear=False)
    def test_encrypted_hex_payload_with_158_protocol_bytes_passes(self):
        client = build_client()
        hex_body = "AA" * 158
        encrypted_body = encrypt_request(hex_body)

        response = client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data=encrypted_body,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(decrypt_response(response.get_data(as_text=True)), "OK")
        entry = server.HISTORY_DATA[-1]
        self.assertEqual(entry["DecryptedTextLength"], 316)
        self.assertEqual(entry["HexTextLength"], 316)
        self.assertEqual(entry["ProtocolByteLength"], 158)
        self.assertEqual(entry["RequestCryptoStatus"], "Decrypted")
        self.assertEqual(entry["ResponseCryptoStatus"], "Encrypted")
        self.assertTrue(entry["LengthPassed"])

    @mock.patch.dict(server.app.config, crypto_config(), clear=False)
    def test_invalid_encrypted_request_returns_encrypted_faile(self):
        client = build_client()

        response = client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data="not-base64!!!",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(decrypt_response(response.get_data(as_text=True)), "faile")
        entry = server.HISTORY_DATA[-1]
        self.assertEqual(entry["ErrorType"], "Decrypt Failed")
        self.assertEqual(entry["RequestCryptoStatus"], "Decrypt failed")
        self.assertEqual(entry["ResponseCryptoStatus"], "Encrypted")
        self.assertFalse(entry["LengthPassed"])

    @mock.patch.dict(server.app.config, crypto_config(), clear=False)
    def test_index_shows_new_crypto_columns(self):
        client = build_client()
        client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data=encrypt_request("AA" * 158),
            content_type="text/plain",
        )

        response = client.get("/")
        html = response.get_data(as_text=True)

        self.assertIn("Raw Body Text Length", html)
        self.assertIn("Decrypted Text Length", html)
        self.assertIn("Hex Text Length", html)
        self.assertIn("Protocol Byte Length", html)
        self.assertIn("Request Crypto", html)
        self.assertIn("Response Crypto", html)
        self.assertIn("AES-128-GCM", html)
        self.assertIn("Version", html)
        self.assertIn(server.APP_VERSION, html)


    def test_generate_key_endpoint_creates_new_aes128_key(self):
        client = build_client()
        with tempfile.TemporaryDirectory() as tmpdir:
            key_store_path = str(Path(tmpdir) / "keys.json")
            with mock.patch.dict(server.app.config, crypto_config(key_store_path), clear=False):
                response = client.post("/keys/generate", data=json.dumps({"name": "device-a"}), content_type="application/json")

                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload["name"], "device-a")
                self.assertEqual(payload["key_length"], 16)
                self.assertEqual(len(bytes.fromhex(payload["key_hex"])), 16)
                self.assertTrue(Path(key_store_path).exists())

                saved = json.loads(Path(key_store_path).read_text(encoding="utf-8"))
                self.assertEqual(saved["active_key_name"], "device-a")
                self.assertIn("device-a", saved["keys"])
                self.assertEqual(saved["keys"]["device-a"]["key_hex"], payload["key_hex"])

    def test_activate_key_endpoint_switches_active_key(self):
        client = build_client()
        with tempfile.TemporaryDirectory() as tmpdir:
            key_store_path = str(Path(tmpdir) / "keys.json")
            store = {
                "active_key_name": "default",
                "keys": {
                    "default": {"key_hex": DEFAULT_TEST_KEY.hex()},
                    "device-b": {"key_hex": "00112233445566778899aabbccddeeff"},
                },
            }
            Path(key_store_path).write_text(json.dumps(store), encoding="utf-8")

            with mock.patch.dict(server.app.config, crypto_config(key_store_path), clear=False):
                response = client.post("/keys/activate", data=json.dumps({"name": "device-b"}), content_type="application/json")

                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertEqual(payload["active_key_name"], "device-b")

                saved = json.loads(Path(key_store_path).read_text(encoding="utf-8"))
                self.assertEqual(saved["active_key_name"], "device-b")

    def test_index_shows_key_management_section(self):
        client = build_client()
        with tempfile.TemporaryDirectory() as tmpdir:
            key_store_path = str(Path(tmpdir) / "keys.json")
            with mock.patch.dict(server.app.config, crypto_config(key_store_path), clear=False):
                response = client.get("/")
                html = response.get_data(as_text=True)

                self.assertIn("Key Management", html)
                self.assertIn("Active Key", html)
                self.assertIn("Generate AES-128 Key", html)
                self.assertIn("Test Usage Guide", html)
                self.assertIn("Failure Reason Map", html)

    @mock.patch.dict(server.app.config, {
        "AES_GCM_KEY": BUILTIN_REQUEST_KEY,
        "AES_GCM_RESPONSE_KEY": BUILTIN_RESPONSE_KEY,
        "AES_GCM_KEY_STORE_PATH": None,
    }, clear=False)
    def test_index_shows_builtin_test_keys(self):
        client = build_client()

        response = client.get("/")
        html = response.get_data(as_text=True)

        self.assertIn("b8286d10dc8ae670189223a299b0affb", html)
        self.assertIn("45e036e26c95279ee61c8f452ee35543", html)

    def test_key_endpoint_rejects_invalid_authorization_header(self):
        client = build_client()
        with tempfile.TemporaryDirectory() as tmpdir:
            key_store_path = str(Path(tmpdir) / "keys.json")
            with mock.patch.dict(server.app.config, crypto_config(key_store_path), clear=False):
                response = client.post(
                    "/keys/generate",
                    data=json.dumps({"name": "device-a"}),
                    content_type="application/json",
                    headers={"Authorization": "Basic invalid"},
                )

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json()["error"], "Authorization header is not in VALID_AUTH_KEYS")


if __name__ == "__main__":
    unittest.main()
