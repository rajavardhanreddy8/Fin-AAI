from __future__ import annotations

import base64
import io
import unittest
from datetime import datetime, timezone
import ssl
import socket
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

from stock_research.collectors.breeze_ohlcv import (
    BREEZE_USER_AGENT,
    _json_request,
    check_breeze_connection,
    completed_five_minute_candles,
    resolve_session_token,
)


class BreezeSessionTests(unittest.TestCase):
    def test_rejects_api_session_when_breeze_does_not_exchange_it(self) -> None:
        with patch("stock_research.collectors.breeze_ohlcv._exchange_api_session", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "valid session token"):
                resolve_session_token({"api_key": "app-key", "api_session": "redirect-session"})

    def test_uses_only_the_session_token_returned_by_breeze(self) -> None:
        token = base64.b64encode(b"user:session-key").decode("ascii")
        with patch("stock_research.collectors.breeze_ohlcv._exchange_api_session", return_value=token) as exchange:
            token = resolve_session_token({"api_key": "app-key", "api_session": "redirect-session"})
        self.assertEqual(token, base64.b64encode(b"user:session-key").decode("ascii"))
        exchange.assert_called_once_with("app-key", "redirect-session")

    def test_accepts_a_pre_exchanged_session_token_without_network_access(self) -> None:
        token = base64.b64encode(b"user:session-key").decode("ascii")
        with patch("stock_research.collectors.breeze_ohlcv._exchange_api_session") as exchange:
            result = resolve_session_token({"api_key": "app-key", "session_token": token})
        self.assertEqual(result, token)
        exchange.assert_not_called()

    def test_extracts_session_from_breeze_redirect_url(self) -> None:
        with patch(
            "stock_research.collectors.breeze_ohlcv._exchange_api_session", return_value=None
        ) as exchange:
            with self.assertRaisesRegex(RuntimeError, "valid session token"):
                resolve_session_token(
                    {"api_key": "app-key", "api_session": "https://localhost/?apisession=redirect-value"}
                )
        exchange.assert_called_once_with("app-key", "redirect-value")

    def test_historical_request_matches_breeze_session_header_format(self) -> None:
        token = base64.b64encode(b"user:session-key").decode("ascii")
        with patch("stock_research.collectors.breeze_ohlcv.resolve_session_token", return_value=token):
            with patch(
                "stock_research.collectors.breeze_ohlcv._json_request", return_value={"Status": 200, "Success": [{"close": 1}]}
            ) as request:
                completed_five_minute_candles(
                    {"api_key": "app-key", "api_session": "redirect"},
                    from_at=datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc),
                    to_at=datetime(2026, 10, 1, 9, 20, tzinfo=timezone.utc),
                )
        headers = request.call_args.args[2]
        payload = request.call_args.args[1]
        self.assertEqual(payload["product_type"], "cash")
        self.assertEqual(payload["exch_code"], "NSE")
        self.assertNotIn("X-Checksum", headers)
        self.assertEqual(headers["apikey"], "app-key")
        self.assertEqual(headers["X-SessionToken"], token)
        self.assertEqual(headers["User-Agent"], BREEZE_USER_AGENT)
        self.assertTrue(request.call_args.kwargs["query_parameters"])

    def test_tls_failure_explains_trusted_ca_without_disabling_verification(self) -> None:
        failure = URLError(ssl.SSLCertVerificationError("self-signed certificate"))
        with patch("stock_research.collectors.breeze_ohlcv.urlopen", side_effect=failure) as open_request:
            with self.assertRaisesRegex(RuntimeError, "BREEZE_CA_BUNDLE"):
                _json_request("https://api.icicidirect.com/test", {}, {})
        context = open_request.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_transient_dns_failure_retries_but_is_bounded(self) -> None:
        failure = URLError(socket.gaierror(11002, "getaddrinfo failed"))
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"Status":200}'
        with patch("stock_research.collectors.breeze_ohlcv.sleep"):
            with patch("stock_research.collectors.breeze_ohlcv.urlopen", side_effect=[failure, response]) as opened:
                self.assertEqual(_json_request("https://api.icicidirect.com/test", {}, {}), {"Status": 200})
                self.assertEqual(opened.call_count, 2)
            with patch("stock_research.collectors.breeze_ohlcv.urlopen", side_effect=failure) as opened:
                with self.assertRaisesRegex(RuntimeError, "after 5 attempts"):
                    _json_request("https://api.icicidirect.com/test", {}, {})
                self.assertEqual(opened.call_count, 5)

    def test_preflight_sends_no_credentials(self) -> None:
        response = HTTPError("https://api.icicidirect.com/test", 401, "Unauthorized", {}, None)
        with patch("stock_research.collectors.breeze_ohlcv.urlopen", side_effect=response) as opened:
            check_breeze_connection()
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "HEAD")
        self.assertIsNone(request.data)
        self.assertEqual(request.headers, {})

    def test_historical_401_explains_the_credential_pair_requirement(self) -> None:
        failure = HTTPError("https://api.icicidirect.com/test", 401, "Unauthorized", {}, None)
        with patch("stock_research.collectors.breeze_ohlcv.urlopen", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "same Breeze app"):
                _json_request("https://breezeapi.icicidirect.com/api/v2/historicalcharts", {}, {})

    def test_historical_401_includes_breeze_reason_without_request_headers(self) -> None:
        failure = HTTPError(
            "https://api.icicidirect.com/test",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"Error":"Checksum mismatch"}'),
        )
        with patch("stock_research.collectors.breeze_ohlcv.urlopen", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "Breeze says: Checksum mismatch"):
                _json_request("https://breezeapi.icicidirect.com/api/v2/historicalcharts", {}, {})


if __name__ == "__main__":
    unittest.main()
