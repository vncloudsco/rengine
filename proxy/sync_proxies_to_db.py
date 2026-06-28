#!/usr/bin/env python3
"""Sync Urban proxy list file into reNgine PostgreSQL (scanengine_proxy)."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time

import psycopg2

DEFAULT_PROXY_FILE = "/data/proxies_curl.txt"
WATCH_POLL_SEC = 30.0


def _log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr)


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _truthy(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def read_proxy_lines(path: str) -> list[str]:
    if not os.path.isfile(path):
        return []
    lines: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("http://") or stripped.startswith("https://"):
                lines.append(stripped)
    return lines


def content_hash(lines: list[str]) -> str:
    payload = "\n".join(lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def connect_db():
    return psycopg2.connect(
        host=_env("POSTGRES_HOST", "db"),
        port=int(_env("POSTGRES_PORT", "5432")),
        dbname=_env("POSTGRES_DB"),
        user=_env("POSTGRES_USER"),
        password=_env("POSTGRES_PASSWORD"),
    )


def sync_to_db(lines: list[str], *, auto_enable: bool) -> bool:
    """Write proxies to scanengine_proxy. Returns True if DB was updated."""
    proxies_text = "\n".join(lines)
    use_proxy = auto_enable and len(lines) > 0

    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM scanengine_proxy ORDER BY id LIMIT 1")
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE scanengine_proxy
                    SET proxies = %s, use_proxy = %s
                    WHERE id = %s
                    """,
                    (proxies_text, use_proxy, row[0]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO scanengine_proxy (use_proxy, proxies)
                    VALUES (%s, %s)
                    """,
                    (use_proxy, proxies_text),
                )
        conn.commit()

    return True


def set_use_proxy(enabled: bool) -> None:
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM scanengine_proxy ORDER BY id LIMIT 1")
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE scanengine_proxy SET use_proxy = %s WHERE id = %s",
                    (enabled, row[0]),
                )
            else:
                cur.execute(
                    "INSERT INTO scanengine_proxy (use_proxy, proxies) VALUES (%s, %s)",
                    (enabled, ""),
                )
        conn.commit()


def run_once(path: str, *, auto_enable: bool, force: bool = False) -> int:
    lines = read_proxy_lines(path)
    file_hash = content_hash(lines)

    state_path = f"{path}.sync_hash"
    last_hash = ""
    if os.path.isfile(state_path):
        with open(state_path, encoding="utf-8") as f:
            last_hash = f.read().strip()

    if not force and file_hash == last_hash and lines:
        _log(f"No changes in {path} ({len(lines)} proxies), skip DB write")
        return 0

    if not lines:
        _log(f"No valid proxies in {path}, skip DB write")
        return 0

    sync_to_db(lines, auto_enable=auto_enable)
    with open(state_path, "w", encoding="utf-8") as f:
        f.write(file_hash)

    _log(
        f"Synced {len(lines)} proxies to scanengine_proxy "
        f"(use_proxy={auto_enable and len(lines) > 0})"
    )
    return 0


def run_watch(path: str, *, auto_enable: bool) -> int:
    _log(f"Watch started: poll every {WATCH_POLL_SEC:g}s -> {path}")
    last_mtime: float | None = None

    while True:
        try:
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if last_mtime is None or mtime != last_mtime:
                    last_mtime = mtime
                    run_once(path, auto_enable=auto_enable, force=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            _log(f"Sync failed: {exc}")
            # Retry on next poll even if the file mtime did not change.
            last_mtime = None

        try:
            time.sleep(WATCH_POLL_SEC)
        except KeyboardInterrupt:
            _log("Watch stopped")
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Urban proxy file into reNgine scanengine_proxy table."
    )
    parser.add_argument(
        "--file",
        "-f",
        default=os.environ.get("PROXY_OUTPUT", DEFAULT_PROXY_FILE),
        help="Proxy list file (one URL per line)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll file and sync when it changes",
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Set use_proxy=false in DB",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force sync even if content hash unchanged",
    )
    args = parser.parse_args()

    auto_enable = _truthy("AUTO_ENABLE_PROXY", True)

    if args.disable:
        set_use_proxy(False)
        _log("Set use_proxy=false in scanengine_proxy")
        return 0

    if args.watch:
        try:
            return run_watch(args.file, auto_enable=auto_enable)
        except KeyboardInterrupt:
            _log("Watch stopped")
            return 0

    return run_once(args.file, auto_enable=auto_enable, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
