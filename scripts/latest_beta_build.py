#!/usr/bin/env python3
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime
from typing import Any

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ios-carrier-bundles-bot/1.0)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def resolve_latest_beta(device: str) -> dict[str, str]:
    url = f"https://api.ipsw.me/v4/device/{device}?type=ipsw"

    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            payload: dict[str, Any] = json.load(response)
    except Exception:
        return {"build": "", "version": "", "url": ""}

    firmwares = payload.get("firmwares") or []
    beta_like = [
        fw for fw in firmwares
        if re.search(r"[a-z]$", str(fw.get("buildid", "")))
    ]

    signed_beta = [fw for fw in beta_like if bool(fw.get("signed"))]
    candidates = signed_beta or beta_like

    if not candidates:
        return resolve_latest_beta_from_ipsw_dev(device)

    latest = max(candidates, key=lambda fw: (parse_dt(fw.get("releasedate")), parse_dt(fw.get("uploaddate"))))
    return {
        "build": str(latest.get("buildid", "")),
        "version": str(latest.get("version", "")),
        "url": str(latest.get("url", "")),
    }


def resolve_latest_beta_from_ipsw_dev(device: str) -> dict[str, str]:
    url = f"https://ipsw.dev/product/version/{device}"

    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return {"build": "", "version": "", "url": ""}

    row_pattern = re.compile(
        r'<tr\s+class="firmware"[^>]*data-signed="(?P<signed>true|false)"[^>]*>.*?'
        r'<strong>\s*(?P<label>[^<]+).*?</strong>.*?'
        r'<div\s+class="build-id"><code>(?P<build>[A-Za-z0-9]+)</code>',
        re.IGNORECASE | re.DOTALL,
    )

    candidates: list[dict[str, str | bool]] = []
    for match in row_pattern.finditer(html):
        label = match.group("label").strip()
        label_lower = label.lower()
        if "beta" not in label_lower and "seed" not in label_lower and "rc" not in label_lower:
            continue

        version_match = re.search(r"(\d+(?:\.\d+){1,2})", label)
        version = version_match.group(1) if version_match else ""
        build = match.group("build").strip()
        signed = match.group("signed").lower() == "true"

        candidates.append({
            "version": version,
            "build": build,
            "signed": signed,
        })

    if not candidates:
        return {"build": "", "version": "", "url": ""}

    signed_candidates = [item for item in candidates if bool(item.get("signed"))]
    selected = signed_candidates[0] if signed_candidates else candidates[0]
    selected_build = str(selected.get("build", ""))
    ipsw_url = resolve_ipsw_url_from_ipsw_dev(device, selected_build)

    return {
        "build": selected_build,
        "version": str(selected.get("version", "")),
        "url": ipsw_url,
    }


def resolve_ipsw_url_from_ipsw_dev(device: str, build: str) -> str:
    if not device or not build:
        return ""

    url = f"https://ipsw.dev/download/{device}/{build}"
    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

    match = re.search(r'https://updates\.cdn-apple\.com[^"\'\s]+\.ipsw', html, re.IGNORECASE)
    return match.group(0) if match else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve latest beta-like iOS build for a device via ipsw.me")
    parser.add_argument("--device", required=True, help="Device identifier, e.g. iPhone18,3")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = resolve_latest_beta(args.device)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
