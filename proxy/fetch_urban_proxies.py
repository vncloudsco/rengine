#!/usr/bin/env python3
"""
Fetch free Urban VPN proxy servers via the same backend API used by the
Urban VPN browser extension (not Urban Browser Guard / Urban Shield).

Urban Browser Guard (this repo) does NOT embed proxy lists. It only talks to
Urban VPN backends for identity, analytics, country checks, and config.
Proxy host/port lists come from stats.falais.com after OAuth-style token flow
against api-pro.urban-vpn.com.

Usage:
    py fetch_urban_proxies.py
    py fetch_urban_proxies.py --output proxies.json
    py fetch_urban_proxies.py --output proxies.txt --format txt
    py fetch_urban_proxies.py --format curl -o proxies_curl.txt
    py fetch_urban_proxies.py --fetch-credentials --workers 20
    py fetch_urban_proxies.py --watch
    py fetch_urban_proxies.py --watch --interval 25 -o proxies_curl.txt --workers 20

Signature: one-time server ticket from the API. Send it with your security token to
accs-proxy to get the HTTP proxy username (password is always "1"). IP:port alone
will not work with curl — you need credentials from signature exchange.

Credentials expire (~30 min for username, ~60 min for security token). When expired,
curl returns HTTP 407. Re-run accs-proxy before expiry, or use UrbanProxySession.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

# Endpoints discovered from Urban VPN extension ecosystem (not hardcoded in Guard source).
API_PRO_BASE = "https://api-pro.urban-vpn.com/rest/v1"
STATS_COUNTRIES_URL = "https://stats.falais.com/api/rest/v2/entrypoints/countries"

DEFAULT_OUTPUT = "urban_proxies.json"
DEFAULT_WATCH_OUTPUT = "proxies_curl.txt"
DEFAULT_WATCH_INTERVAL_MIN = 25.0
CLIENT_APP = "URBAN_VPN_BROWSER_EXTENSION"
BROWSER = "CHROME"
# Default URL in generated curl one-liner (change when copying if needed).
CURL_TEST_URL = "https://api.ipify.org?format=json"
# Urban VPN Chrome extension ID (used as Origin header by community tools).
EXTENSION_ORIGIN = "chrome-extension://eppiocemhmnlbhjplcgkofciiegomcon"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Origin": EXTENSION_ORIGIN,
}


@dataclass
class ProxyServer:
    country_code: str
    country_name: str
    server_name: str
    server_type: str
    host: str
    ip: str
    port: int
    pool: str
    weight: int
    signature: str
    signature_expiration_time: int | None = None
    username: str | None = None
    password: str | None = None
    username_expiration_time: int | None = None

    @property
    def username_expires_in_minutes(self) -> float | None:
        if not self.username_expiration_time:
            return None
        return max(0.0, (self.username_expiration_time - time.time() * 1000) / 60_000)

    @property
    def proxy_url(self) -> str:
        if self.username:
            pwd = self.password or "1"
            return f"http://{self.username}:{pwd}@{self.ip}:{self.port}"
        return f"http://{self.ip}:{self.port}"

    @property
    def url_config(self) -> str | None:
        """Ready-to-run curl one-liner; null until username is fetched."""
        if not self.username:
            return None
        return f'curl -x "{self.proxy_url}" "{CURL_TEST_URL}"'

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["url_config"] = self.url_config
        data["username_expires_in_minutes"] = (
            round(self.username_expires_in_minutes, 1)
            if self.username_expires_in_minutes is not None
            else None
        )
        return data


class UrbanVpnClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self._anon_token: str | None = None
        self._security_token: str | None = None

    def _request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        headers = dict(DEFAULT_HEADERS)
        if extra_headers:
            headers.update(extra_headers)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        if data is None and method == "GET":
            headers.pop("Content-Type", None)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc

    def register_anonymous(self) -> str:
        payload = {"clientApp": {"name": CLIENT_APP, "browser": BROWSER}}
        url = (
            f"{API_PRO_BASE}/registrations/clientApps/"
            f"{CLIENT_APP}/users/anonymous"
        )
        result = self._request("POST", url, payload)
        token = result.get("value")
        if not token:
            raise RuntimeError(f"Anonymous registration failed: {result}")
        self._anon_token = token
        return token

    def get_security_token(self, anon_token: str | None = None) -> str:
        token = anon_token or self._anon_token
        if not token:
            token = self.register_anonymous()
        payload = {"type": "accs", "clientApp": {"name": CLIENT_APP}}
        result = self._request(
            "POST",
            f"{API_PRO_BASE}/security/tokens/accs",
            payload,
            {"Authorization": f"Bearer {token}"},
        )
        sec = result.get("value")
        if not sec:
            raise RuntimeError(f"Security token request failed: {result}")
        self._security_token = sec
        return sec

    def get_countries(self, security_token: str | None = None) -> list[dict[str, Any]]:
        sec = security_token or self._security_token
        if not sec:
            sec = self.get_security_token()
        result = self._request(
            "GET",
            STATS_COUNTRIES_URL,
            extra_headers={
                "Authorization": f"Bearer {sec}",
                "x-client-app": CLIENT_APP,
            },
        )
        countries = result.get("countries", {}).get("elements", [])
        if not countries:
            raise RuntimeError(f"No countries in response: {result}")
        return countries

    def get_proxy_credential(
        self, security_token: str, signature: str
    ) -> tuple[str, int | None]:
        payload = {
            "type": "accs-proxy",
            "clientApp": {"name": CLIENT_APP},
            "signature": signature,
        }
        result = self._request(
            "POST",
            f"{API_PRO_BASE}/security/tokens/accs-proxy",
            payload,
            {"Authorization": f"Bearer {security_token}"},
        )
        username = result.get("value")
        if not username:
            raise RuntimeError(f"Proxy credential request failed: {result}")
        return username, result.get("expirationTime")


class UrbanProxySession:
    """Keep one Urban VPN proxy usable by refreshing tokens before they expire."""

    REFRESH_USERNAME_BEFORE_MIN = 25
    REFRESH_SECURITY_BEFORE_MIN = 50

    def __init__(self, ip: str | None = None, port: int | None = None) -> None:
        self.client = UrbanVpnClient()
        self.target_ip = ip
        self.target_port = port
        self._security_token: str | None = None
        self._security_expiration_ms: int | None = None
        self._signature: str | None = None
        self._signature_expiration_ms: int | None = None
        self._username: str | None = None
        self._username_expiration_ms: int | None = None
        self._server_ip: str | None = None
        self._server_port: int | None = None

    def _ensure_security_token(self) -> str:
        now_ms = time.time() * 1000
        if (
            self._security_token
            and self._security_expiration_ms
            and (self._security_expiration_ms - now_ms) > self.REFRESH_SECURITY_BEFORE_MIN * 60_000
        ):
            return self._security_token

        self.client.register_anonymous()
        payload = {"type": "accs", "clientApp": {"name": CLIENT_APP}}
        result = self.client._request(
            "POST",
            f"{API_PRO_BASE}/security/tokens/accs",
            payload,
            {"Authorization": f"Bearer {self.client._anon_token}"},
        )
        self._security_token = result["value"]
        self._security_expiration_ms = result.get("expirationTime")
        return self._security_token

    def _pick_server(self, countries: list[dict[str, Any]]) -> tuple[str, int, str, int | None]:
        for country in countries:
            for server in country.get("servers", {}).get("elements", []):
                address = server.get("address", {}).get("primary", {})
                ip = address.get("ip") or address.get("host")
                port = address.get("port")
                signature = server.get("signature")
                if not ip or not port or not signature:
                    continue
                if self.target_ip and ip != self.target_ip:
                    continue
                if self.target_port and int(port) != self.target_port:
                    continue
                return ip, int(port), signature, server.get("signatureExpirationTime")
        raise RuntimeError("No matching proxy server found")

    def _ensure_signature(self) -> tuple[str, int, str]:
        now_ms = time.time() * 1000
        if (
            self._signature
            and self._server_ip
            and self._server_port
            and self._signature_expiration_ms
            and (self._signature_expiration_ms - now_ms) > 2 * 60_000
        ):
            return self._server_ip, self._server_port, self._signature

        security_token = self._ensure_security_token()
        countries = self.client.get_countries(security_token)
        ip, port, signature, sig_exp = self._pick_server(countries)
        self._server_ip = ip
        self._server_port = port
        self._signature = signature
        self._signature_expiration_ms = sig_exp
        return ip, port, signature

    def refresh(self) -> ProxyServer:
        security_token = self._ensure_security_token()
        ip, port, signature = self._ensure_signature()
        username, username_exp = self.client.get_proxy_credential(
            security_token, signature
        )
        self._username = username
        self._username_expiration_ms = username_exp
        return ProxyServer(
            country_code="",
            country_name="",
            server_name="",
            server_type="PROXY",
            host=ip,
            ip=ip,
            port=port,
            pool="",
            weight=0,
            signature=signature,
            signature_expiration_time=self._signature_expiration_ms,
            username=username,
            password="1",
            username_expiration_time=username_exp,
        )

    def get_proxy_url(self) -> str:
        now_ms = time.time() * 1000
        if (
            not self._username
            or not self._username_expiration_ms
            or (self._username_expiration_ms - now_ms)
            < self.REFRESH_USERNAME_BEFORE_MIN * 60_000
        ):
            return self.refresh().proxy_url
        return ProxyServer(
            country_code="",
            country_name="",
            server_name="",
            server_type="PROXY",
            host=self._server_ip or "",
            ip=self._server_ip or "",
            port=self._server_port or 8081,
            pool="",
            weight=0,
            signature=self._signature or "",
            username=self._username,
            password="1",
            username_expiration_time=self._username_expiration_ms,
        ).proxy_url


def _country_code(country: dict[str, Any]) -> str:
    code = country.get("code", "")
    if isinstance(code, dict):
        return code.get("iso2") or code.get("iso3") or ""
    return str(code)


def _build_server_row(
    country: dict[str, Any],
    server: dict[str, Any],
    username: str | None = None,
) -> ProxyServer | None:
    address = server.get("address", {}).get("primary", {})
    ip = address.get("ip") or address.get("host")
    port = address.get("port")
    signature = server.get("signature")
    if not ip or not port or not signature:
        return None
    return ProxyServer(
        country_code=_country_code(country),
        country_name=country.get("title", ""),
        server_name=server.get("name", ""),
        server_type=server.get("type", ""),
        host=address.get("host", ip),
        ip=ip,
        port=int(port),
        pool=server.get("pool", ""),
        weight=int(server.get("weight", 0)),
        signature=signature,
        signature_expiration_time=server.get("signatureExpirationTime"),
        username=username,
        password="1" if username else None,
    )


def parse_servers(
    countries: list[dict[str, Any]],
    fetch_credentials: bool,
    client: UrbanVpnClient,
    security_token: str,
    workers: int = 12,
) -> list[ProxyServer]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for country in countries:
        for server in country.get("servers", {}).get("elements", []):
            rows.append((country, server))

    if not fetch_credentials:
        return [
            s
            for country, server in rows
            if (s := _build_server_row(country, server)) is not None
        ]

    servers: list[ProxyServer] = []
    failed = 0

    def fetch_one(item: tuple[dict[str, Any], dict[str, Any]]) -> ProxyServer | None:
        country, server = item
        row = _build_server_row(country, server)
        if row is None:
            return None
        try:
            username, username_exp = client.get_proxy_credential(
                security_token, row.signature
            )
            row.username = username
            row.password = "1"
            row.username_expiration_time = username_exp
            return row
        except RuntimeError:
            return None

    total = len(rows)
    print(
        f"Fetching credentials for {total} servers ({workers} workers)...",
        file=sys.stderr,
    )
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, item): item for item in rows}
        for future in as_completed(futures):
            result = future.result()
            done += 1
            if result is None:
                failed += 1
            else:
                servers.append(result)
            if done % 25 == 0 or done == total:
                print(f"  {done}/{total} done", file=sys.stderr)

    if failed:
        print(f"Warning: {failed} servers skipped (missing data or auth failed)", file=sys.stderr)
    servers.sort(key=lambda s: (s.country_name, s.server_name))
    return servers


def fetch_all_proxies(
    client: UrbanVpnClient,
    fetch_credentials: bool,
    workers: int,
) -> tuple[list[ProxyServer], list[dict[str, Any]]]:
    print("Registering anonymous user...", file=sys.stderr)
    client.register_anonymous()
    print("Getting security token...", file=sys.stderr)
    security_token = client.get_security_token()
    print("Fetching country/server list...", file=sys.stderr)
    countries = client.get_countries(security_token)
    servers = parse_servers(
        countries,
        fetch_credentials,
        client,
        security_token,
        workers=max(1, workers),
    )
    return servers, countries


def write_output(servers: list[ProxyServer], path: str, fmt: str) -> None:
    if fmt in ("txt", "curl"):
        usable = [s for s in servers if s.username] if fmt == "curl" else servers
        lines = [s.proxy_url for s in usable]
        content = "\n".join(lines) + ("\n" if lines else "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        payload = {
            "source": "urban-vpn-api",
            "client_app": CLIENT_APP,
            "total": len(servers),
            "proxies": [s.to_dict() for s in servers],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")


def write_output_atomic(servers: list[ProxyServer], path: str, fmt: str) -> None:
    tmp_path = f"{path}.tmp"
    write_output(servers, tmp_path, fmt)
    os.replace(tmp_path, path)


def _log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr)


def run_watch(output: str, workers: int, interval_min: float) -> int:
    _log(
        f"Watch started: refresh every {interval_min:g} min -> {output} "
        f"(Ctrl+C to stop)"
    )
    while True:
        try:
            client = UrbanVpnClient()
            servers, countries = fetch_all_proxies(
                client, fetch_credentials=True, workers=workers
            )
            write_output_atomic(servers, output, "curl")
            _log(
                f"Wrote {len(servers)} proxies from {len(countries)} countries "
                f"to {output}"
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            _log(f"Refresh failed: {exc}")

        try:
            time.sleep(max(1.0, interval_min * 60))
        except KeyboardInterrupt:
            _log("Watch stopped")
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Urban VPN free proxy list from official API."
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT}, {DEFAULT_WATCH_OUTPUT} with --watch)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "txt", "curl"),
        default="json",
        help="json=full data; txt=ip:port lines; curl=auth proxy URLs for curl (default: json)",
    )
    parser.add_argument(
        "--fetch-credentials",
        action="store_true",
        help="Request per-server proxy auth username (required for curl)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Parallel credential requests (default: 12)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Loop forever: refresh credentials and rewrite curl proxy list",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_WATCH_INTERVAL_MIN,
        help="Watch refresh interval in minutes (default: 25)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print summary to stdout",
    )
    args = parser.parse_args()

    if args.watch:
        args.fetch_credentials = True
        args.format = "curl"
        if args.output == DEFAULT_OUTPUT:
            args.output = DEFAULT_WATCH_OUTPUT
        try:
            return run_watch(
                output=args.output,
                workers=max(1, args.workers),
                interval_min=max(1.0, args.interval),
            )
        except KeyboardInterrupt:
            _log("Watch stopped")
            return 0

    if args.format == "curl":
        args.fetch_credentials = True

    client = UrbanVpnClient()
    servers, countries = fetch_all_proxies(
        client,
        args.fetch_credentials,
        workers=max(1, args.workers),
    )

    write_output(servers, args.output, args.format)

    summary = (
        f"Saved {len(servers)} proxies from {len(countries)} countries "
        f"to {args.output}"
    )
    print(summary, file=sys.stderr)

    if args.print:
        for s in servers[:10]:
            line = s.url_config or s.proxy_url
            print(line)
        if len(servers) > 10:
            print(f"... and {len(servers) - 10} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
