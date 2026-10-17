"""Data-only Breeze candle collector for the isolated fin-AAI AWS host.

This module deliberately has no broker order, holdings, funds, or position API
paths.  It accepts completed historical candles only and writes the raw response
to the pilot's private S3 evidence store.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import socket
import ssl
from time import sleep
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


CUSTOMER_DETAILS_URL = "https://api.icicidirect.com/breezeapi/api/v1/customerdetails"
HISTORICAL_CHARTS_URL = "https://breezeapi.icicidirect.com/api/v2/historicalcharts"
ALLOWED_INTERVAL = "5minute"
BREEZE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_5_8) AppleWebKit/534.50.2 "
    "(KHTML, like Gecko) Version/5.0.6 Safari/533.22.3"
)


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetimes must include a timezone")
    # V2 expects exchange-clock values with a literal Z, as in the SDK examples.
    return value.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _open_request(request: Request):
    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        pass  # The platform store remains verified when the optional bundle is absent.
    else:
        context.load_verify_locations(cafile=certifi.where())
    ca_bundle = os.environ.get("BREEZE_CA_BUNDLE", "").strip()
    if ca_bundle:
        try:
            context.load_verify_locations(cafile=ca_bundle)
        except (OSError, ssl.SSLError) as error:
            raise RuntimeError("BREEZE_CA_BUNDLE must point to a valid trusted CA PEM file.") from error
    for attempt in range(5):
        try:
            return urlopen(request, timeout=30, context=context)  # nosec B310: endpoint constants above
        except URLError as error:
            if isinstance(error.reason, socket.gaierror):
                if attempt < 4:
                    sleep(attempt + 1)
                    continue
                raise RuntimeError(
                    "Breeze or your proxy could not be resolved after 5 attempts. "
                    "Check your internet connection, VPN/proxy and DNS, then retry."
                ) from error
            if isinstance(error.reason, ssl.SSLCertVerificationError):
                raise RuntimeError(
                    "Breeze TLS certificate verification failed. If your network uses TLS inspection, "
                    "set BREEZE_CA_BUNDLE to the trusted CA certificate in PEM format."
                ) from error
            raise


def check_breeze_connection() -> None:
    """Check the same HTTPS path without sending any credentials."""
    try:
        with _open_request(Request(CUSTOMER_DETAILS_URL, method="HEAD")):
            pass
    except HTTPError as error:
        # A 4xx response still proves DNS and verified TLS worked.
        if error.code >= 500:
            raise RuntimeError(f"Breeze connection check returned HTTP {error.code}; retry later.") from error


def _json_request(
    url: str, payload: dict[str, Any], headers: dict[str, str], *, query_parameters: bool = False
) -> dict[str, Any]:
    body = None if query_parameters else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    target = f"{url}?{urlencode(payload)}" if query_parameters else url
    request = Request(target, data=body, headers=headers, method="GET")
    try:
        with _open_request(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 401 and url == HISTORICAL_CHARTS_URL:
            detail = ""
            try:
                body = json.loads(error.read().decode("utf-8"))
                service_error = body.get("Error") if isinstance(body, dict) else None
                if isinstance(service_error, str) and service_error.strip():
                    for value in headers.values():
                        if value:
                            service_error = service_error.replace(value, "[redacted]")
                    detail = f" Breeze says: {service_error.strip()[:300]}"
            except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                pass
            raise RuntimeError(
                "Breeze rejected historical-data authentication (HTTP 401). "
                "Use an App Key, Secret Key, and fresh API session from the same Breeze app."
                + detail
            ) from error
        raise


def _exchange_api_session(api_key: str, api_session: str) -> str | None:
    response = _json_request(
        CUSTOMER_DETAILS_URL,
        {"SessionToken": api_session, "AppKey": api_key},
        {"Content-Type": "application/json"},
    )
    success = response.get("Success")
    token = success.get("session_token") if isinstance(success, dict) else None
    return _canonical_session_token(token) if isinstance(token, str) else None


def _canonical_session_token(token: str) -> str:
    """Validate and rebuild Breeze's base64 ``user_id:session_key`` header."""

    try:
        user_id, session_key = base64.b64decode(token, validate=True).decode("ascii").split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise RuntimeError("Breeze returned a malformed session token") from error
    if not user_id or not session_key:
        raise RuntimeError("Breeze returned a malformed session token")
    return base64.b64encode(f"{user_id}:{session_key}".encode("ascii")).decode("ascii")


def _api_session_value(value: str) -> str:
    """Accept either Breeze's raw value or its localhost redirect URL."""

    if "://" not in value:
        return value
    parsed = parse_qs(urlsplit(value).query).get("apisession", [])
    if len(parsed) != 1 or not parsed[0].strip():
        raise ValueError("Breeze redirect URL must contain one apisession value")
    return parsed[0].strip()


def resolve_session_token(secret: dict[str, str]) -> str:
    """Use an API session when supplied, otherwise accept an already-derived token.

    This supports the Breeze redirect value and the session-token value returned by
    Breeze's customer-details endpoint without logging either value.
    """

    api_key = secret.get("api_key", "").strip()
    supplied = secret.get("api_session", secret.get("session_token", "")).strip()
    if not api_key or not supplied:
        raise ValueError("Breeze secret needs api_key and api_session or session_token")
    if "api_session" not in secret:
        return _canonical_session_token(supplied)
    exchanged = _exchange_api_session(api_key, _api_session_value(supplied))
    if not exchanged:
        raise RuntimeError("Breeze did not return a valid session token for this API session")
    return exchanged


def completed_five_minute_candles(
    secret: dict[str, str], *, from_at: datetime, to_at: datetime, stock_code: str = "NIFBEE"
) -> dict[str, Any]:
    """Fetch only NSE cash 5-minute historical candles from the Breeze API."""

    if from_at >= to_at:
        raise ValueError("from_at must precede to_at")

    session_token = resolve_session_token(secret)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload = {
        "interval": ALLOWED_INTERVAL,
        "from_date": _iso_timestamp(from_at),
        "to_date": _iso_timestamp(to_at),
        "stock_code": stock_code,
        "exch_code": "NSE",
        "product_type": "cash",
    }
    response = _json_request(
        HISTORICAL_CHARTS_URL,
        payload,
        {
            "Content-Type": "application/json",
            "apikey": secret["api_key"],
            "X-SessionToken": session_token,
            "User-Agent": BREEZE_USER_AGENT,
        },
        query_parameters=True,
    )
    if response.get("Status") != 200 or not isinstance(response.get("Success"), list):
        raise RuntimeError("Breeze did not return historical candle data")
    if not response["Success"]:
        raise RuntimeError("Breeze returned zero candles for this time range; no snapshot was uploaded")
    return {"retrieved_at": timestamp, "request": payload, "response": response}


def save_raw_snapshot(snapshot: dict[str, Any], *, bucket: str, key: str) -> str:
    """Save one immutable raw source snapshot through the collector instance role."""

    import boto3  # Installed only on the dedicated AWS collector host.

    encoded = json.dumps(snapshot, separators=(",", ":"), sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=encoded,
        ContentType="application/json",
        Metadata={"sha256": content_hash, "schema-version": "1"},
    )
    return content_hash
