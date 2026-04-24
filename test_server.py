import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("server.py")
spec = importlib.util.spec_from_file_location("uynb_server", MODULE_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def build_client():
    server.app.config["TESTING"] = True
    server.HISTORY_DATA.clear()
    return server.app.test_client()


class ServerTests(unittest.TestCase):
    def test_hex_payload_with_158_protocol_bytes_passes(self):
        client = build_client()
        hex_body = "AA" * 158

        response = client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data=hex_body,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "OK")
        entry = server.HISTORY_DATA[-1]
        self.assertEqual(entry["RawBodyTextLength"], 316)
        self.assertEqual(entry["HexTextLength"], 316)
        self.assertEqual(entry["ProtocolByteLength"], 158)
        self.assertEqual(entry["HexDecodeStatus"], "OK")
        self.assertTrue(entry["LengthPassed"])

    def test_non_hex_payload_fails_with_not_hex_text(self):
        client = build_client()

        response = client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data="POST /HMWSSBAPI/PostMeterReadingData HTTP/1.1",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_data(as_text=True), "faile")
        entry = server.HISTORY_DATA[-1]
        self.assertEqual(entry["ErrorType"], "Not Hex Text")
        self.assertEqual(entry["HexDecodeStatus"], "Not hex text")
        self.assertFalse(entry["LengthPassed"])

    def test_index_shows_new_length_columns(self):
        client = build_client()
        client.post(
            "/HMWSSBAPI/PostMeterReadingData",
            data="AA" * 158,
            content_type="text/plain",
        )

        response = client.get("/")
        html = response.get_data(as_text=True)

        self.assertIn("Raw Body Text Length", html)
        self.assertIn("Hex Text Length", html)
        self.assertIn("Protocol Byte Length", html)
        self.assertIn("Decode Status", html)


if __name__ == "__main__":
    unittest.main()
