#!/usr/bin/env python3
"""
Generate a machine-readable JSON report of Portugal carrier bundle changes.
Compares the previous commit to HEAD (or specified commits).
"""
import json
import subprocess
import sys
from datetime import datetime, timezone

# Default to comparing HEAD~1 with HEAD
commit = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
prev_commit = sys.argv[2] if len(sys.argv) > 2 else f"{commit}~1"

def plutil_to_dict(commit_ref, filepath):
    try:
        result = subprocess.run(
            ["git", "show", f"{commit_ref}:{filepath}"],
            capture_output=True, cwd="/Users/andre/Desktop/ios-carrier-bundles"
        )
        if result.returncode != 0:
            return None
        
        result2 = subprocess.run(
            ["plutil", "-convert", "json", "-o", "-", "-"],
            input=result.stdout,
            capture_output=True
        )
        if result2.returncode == 0:
            return json.loads(result2.stdout.decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}", file=__import__('sys').stderr)
    return None

changes = {
    "report_generated": datetime.now(timezone.utc).isoformat(),
    "ios_version": "26.4",
    "ios_build": "23E5218e",
    "ios_release": "iOS 26.4 beta 2",
    "release_date": "2026-02-23",
    "commit_sha": commit,
    "country": "Portugal",
    "country_code": "PT",
    "bundles_changed": []
}

# Country bundle
country_old = plutil_to_dict(prev_commit, "Country Bundles/Portugal.bundle/Info.plist")
country_new = plutil_to_dict(commit, "Country Bundles/Portugal.bundle/Info.plist")

if country_old and country_new:
    changes["bundles_changed"].append({
        "type": "country",
        "name": "Portugal",
        "bundle_id": country_new.get("CFBundleIdentifier"),
        "version_old": country_old.get("CFBundleVersion"),
        "version_new": country_new.get("CFBundleVersion"),
        "files_modified": ["Info.plist", "signatures/common.plist"]
    })

# Carrier bundles
carriers = ["Optimus_pt", "TMN_pt", "Vodafone_pt"]
for carrier in carriers:
    old = plutil_to_dict(prev_commit, f"Carrier Bundles/{carrier}.bundle/Info.plist")
    new = plutil_to_dict(commit, f"Carrier Bundles/{carrier}.bundle/Info.plist")
    
    if old and new:
        files_result = subprocess.run(
            ["git", "diff", "--name-only", prev_commit, commit],
            capture_output=True, text=True
        )
        modified = [f.split("/")[-1] for f in files_result.stdout.strip().split("\n") 
                   if f"/{carrier}.bundle/" in f and f]
        
        changes["bundles_changed"].append({
            "type": "carrier",
            "name": carrier.replace("_pt", ""),
            "bundle_id": new.get("CFBundleIdentifier"),
            "version_old": old.get("CFBundleVersion"),
            "version_new": new.get("CFBundleVersion"),
            "files_modified": sorted(modified)
        })

print(json.dumps(changes, indent=2))
