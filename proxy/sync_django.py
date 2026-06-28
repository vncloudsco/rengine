#!/usr/bin/env python3
"""Push proxy file into reNgine using Django ORM (run inside web container)."""

from __future__ import annotations

import os
import sys


def _bootstrap_django_app() -> None:
    """Ensure reNgine package is importable when script is outside /usr/src/app."""
    app_root = os.environ.get("RENGINE_APP_ROOT", "/usr/src/app")
    if os.path.isdir(app_root):
        if app_root not in sys.path:
            sys.path.insert(0, app_root)
        os.chdir(app_root)


def _truthy(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Set use_proxy=false on the Proxy row (same as UI unchecked).",
    )
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reNgine.settings")
    _bootstrap_django_app()

    import django

    django.setup()

    from scanEngine.models import Proxy

    if args.disable:
        proxy = Proxy.objects.first()
        if proxy is None:
            proxy = Proxy()
        proxy.use_proxy = False
        proxy.save()
        print(
            f"Disabled proxy via Django ORM "
            f"(table={Proxy._meta.db_table}, use_proxy=False, id={proxy.pk})"
        )
        return 0

    path = os.environ.get("PROXY_FILE", "/usr/src/urban_proxies/proxies_curl.txt")
    auto_enable = _truthy("AUTO_ENABLE_PROXY", True)

    if not os.path.isfile(path):
        print(f"Proxy file not found: {path}", file=sys.stderr)
        return 1

    lines: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("http://") or stripped.startswith("https://"):
                lines.append(stripped)

    if not lines:
        print(f"No valid proxies in {path}", file=sys.stderr)
        return 1

    proxy = Proxy.objects.first()
    if proxy is None:
        proxy = Proxy()

    proxy.proxies = "\n".join(lines)
    proxy.use_proxy = auto_enable and bool(lines)
    proxy.save()

    print(
        f"Synced {len(lines)} proxies via Django ORM "
        f"(table={Proxy._meta.db_table}, use_proxy={proxy.use_proxy}, id={proxy.pk})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
