#!/usr/bin/env python3
"""
Resolve download URL for specific iOS build ID.
Queries ipsw.me and ips.dev APIs to find beta/release builds.
"""
import argparse
import json
import re
import sys
import urllib.request
from typing import Any

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ios-carrier-bundles-bot/1.0)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


def resolve_from_ipsw_me(device: str, build: str) -> dict[str, str]:
    """Query ipsw.me API for specific build."""
    url = f"https://api.ipsw.me/v4/device/{device}?type=ipsw"
    
    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            payload: dict[str, Any] = json.load(response)
    except Exception as e:
        print(f"ipsw.me API error: {e}", file=sys.stderr)
        return {"build": "", "version": "", "url": ""}
    
    firmwares = payload.get("firmwares") or []
    
    for fw in firmwares:
        if str(fw.get("buildid", "")).lower() == build.lower():
            return {
                "build": str(fw.get("buildid", "")),
                "version": str(fw.get("version", "")),
                "url": str(fw.get("url", ""))
            }
    
    return {"build": "", "version": "", "url": ""}


def resolve_from_ipsw_dev(device: str, build: str) -> dict[str, str]:
    """Query ipsw.dev API for specific build."""
    url = f"https://api.ipsw.dev/v1/firmwares/{device}"
    
    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            firmwares: list[dict[str, Any]] = json.load(response)
    except Exception as e:
        print(f"ipsw.dev API error: {e}", file=sys.stderr)
        return {"build": "", "version": "", "url": ""}
    
    for fw in firmwares:
        if str(fw.get("buildid", "")).lower() == build.lower():
            return {
                "build": str(fw.get("buildid", "")),
                "version": str(fw.get("version", "")),
                "url": str(fw.get("url", ""))
            }
    
    return {"build": "", "version": "", "url": ""}


def resolve_from_ipsw_dev_download_page(device: str, build: str) -> dict[str, str]:
    """Query ipsw.dev download page and scrape direct Apple CDN URL.

    This avoids dependency on api.ipsw.dev DNS availability.
    """
    url = f"https://ipsw.dev/download/{device}/{build}"

    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"ipsw.dev download page error: {e}", file=sys.stderr)
        return {"build": "", "version": "", "url": ""}

    match = re.search(r'https://updates\.cdn-apple\.com[^"\'\s]+\.ipsw', html, re.IGNORECASE)
    if not match:
        return {"build": "", "version": "", "url": ""}

    version_match = re.search(r'Version\s*</span>\s*<span[^>]*>\s*([^<]+)\s*<', html, re.IGNORECASE)
    version = version_match.group(1).strip() if version_match else ""

    return {
        "build": build,
        "version": version,
        "url": match.group(0),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Resolve iOS build ID to download URL"
    )
    parser.add_argument(
        "--device",
        required=True,
        help="Device identifier (e.g., iPhone18,3)"
    )
    parser.add_argument(
        "--build",
        required=True,
        help="iOS build ID (e.g., 23E5211a)"
    )
    
    args = parser.parse_args()
    
    # Try ipsw.me first
    result = resolve_from_ipsw_me(args.device, args.build)
    
    # Fallback to ipsw.dev API
    if not result["url"]:
        result = resolve_from_ipsw_dev(args.device, args.build)

    # Final fallback to ipsw.dev HTML page scraping
    if not result["url"]:
        result = resolve_from_ipsw_dev_download_page(args.device, args.build)
    
    if not result["url"]:
        print(f"Could not resolve build {args.build} for device {args.device}", file=sys.stderr)
        sys.exit(1)
    
    print(json.dumps(result))


if __name__ == "__main__":
    main()
