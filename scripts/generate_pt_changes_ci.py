#!/usr/bin/env python3
"""
Generate a machine-readable JSON report of Portugal carrier bundle changes.
This version is for CI and compares directories instead of git commits.
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

if len(sys.argv) < 3:
    print("Usage: generate_pt_changes_ci.py <base_dir> <head_dir>", file=sys.stderr)
    sys.exit(1)

base_dir = Path(sys.argv[1])
head_dir = Path(sys.argv[2])

def plutil_to_dict(bundle_path):
    """Convert plist to dict from a file path."""
    try:
        result = subprocess.run(
            ["plutil", "-convert", "json", "-o", "-", str(bundle_path)],
            capture_output=True
        )
        if result.returncode == 0:
            return json.loads(result.stdout.decode('utf-8'))
    except:
        pass
    return None

changes = {
    "report_generated": datetime.now(timezone.utc).isoformat(),
    "country": "Portugal",
    "country_code": "PT",
    "bundles_changed": []
}

# Get iOS version from head metadata
metadata_path = head_dir / "ipsw_metadata.json"
if metadata_path.exists():
    try:
        metadata = json.loads(metadata_path.read_text())
        changes["ios_version"] = metadata.get("version", "unknown")
        changes["ios_build"] = metadata.get("build", "unknown")
        os_type = metadata.get("os", "")
        build = changes["ios_build"]
        if build[-1:].isalpha() or any(x in os_type.lower() for x in ['development', 'beta', 'seed']):
            changes["ios_release"] = f"iOS {changes['ios_version']} beta"
        else:
            changes["ios_release"] = f"iOS {changes['ios_version']}"
    except:
        pass

# Country bundle
base_country = plutil_to_dict(base_dir / "Country Bundles/Portugal.bundle/Info.plist")
head_country = plutil_to_dict(head_dir / "Country Bundles/Portugal.bundle/Info.plist")

if base_country and head_country:
    changes["bundles_changed"].append({
        "type": "country",
        "name": "Portugal",
        "bundle_id": head_country.get("CFBundleIdentifier"),
        "version_old": base_country.get("CFBundleVersion"),
        "version_new": head_country.get("CFBundleVersion")
    })

# Carrier bundles
for bundle_name in ["Optimus_pt", "TMN_pt", "Vodafone_pt"]:
    base_info = plutil_to_dict(base_dir / f"Carrier Bundles/{bundle_name}.bundle/Info.plist")
    head_info = plutil_to_dict(head_dir / f"Carrier Bundles/{bundle_name}.bundle/Info.plist")
    
    if base_info and head_info:
        changes["bundles_changed"].append({
            "type": "carrier",
            "name": bundle_name.replace("_pt", ""),
            "bundle_id": head_info.get("CFBundleIdentifier"),
            "version_old": base_info.get("CFBundleVersion"),
            "version_new": head_info.get("CFBundleVersion")
        })

if changes["bundles_changed"]:
    print(json.dumps(changes, indent=2))
else:
    print("{}")
