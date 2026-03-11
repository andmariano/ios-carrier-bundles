#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import plistlib
from typing import Any

PLIST_SUFFIXES = {".plist", ".mobileconfig"}


def sha256sum(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_bundle_dirs(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {entry.name for entry in root.iterdir() if entry.is_dir() and entry.name.endswith(".bundle")}


def list_files(bundle_dir: Path) -> set[str]:
    if not bundle_dir.exists():
        return set()
    paths: set[str] = set()
    for path in bundle_dir.rglob("*"):
        if path.is_file():
            paths.add(str(path.relative_to(bundle_dir)).replace("\\", "/"))
    return paths


def try_read_plist(path: Path) -> Any | None:
    if path.suffix.lower() not in PLIST_SUFFIXES:
        return None
    try:
        with path.open("rb") as handle:
            return plistlib.load(handle)
    except Exception:
        return None


def flatten_schema(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()

    if isinstance(value, dict):
        if not value and prefix:
            paths.add(prefix)
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.update(flatten_schema(child, child_prefix))
        return paths

    if isinstance(value, list):
        list_prefix = f"{prefix}[]" if prefix else "[]"
        if not value:
            paths.add(list_prefix)
            return paths
        for item in value:
            paths.update(flatten_schema(item, list_prefix))
        return paths

    if prefix:
        paths.add(prefix)
    return paths


def summarize_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines: list[str] = []

    lines.append("# Carrier Bundle Change Report")
    lines.append("")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- New carriers detected: {summary['new_carriers_detected']}")
    lines.append(f"- New plist keys detected: {summary['new_keys_detected']}")
    lines.append("")

    if report["new_carriers"]:
        lines.append("## New Carriers")
        for bundle in report["new_carriers"]:
            lines.append(f"- {bundle}")
        lines.append("")

    if report["new_tags_by_bundle"]:
        lines.append("## New Tags By Bundle")
        for item in report["new_tags_by_bundle"]:
            lines.append(f"### {item['bundle']}")
            lines.append(f"- New plist keys: {len(item['new_key_paths'])}")
            lines.append("")

    if report["new_tags"]:
        lines.append("## Newly Detected Plist Keys")
        for key_path in report["new_tags"]:
            lines.append(f"- {key_path}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_report(old_root: Path, new_root: Path, max_key_entries: int) -> dict[str, Any]:
    old_bundles = list_bundle_dirs(old_root)
    new_bundles = list_bundle_dirs(new_root)

    new_carriers = sorted(new_bundles - old_bundles)
    common_bundles = sorted(old_bundles & new_bundles)

    new_tags_by_bundle: list[dict[str, Any]] = []
    all_new_key_paths: set[str] = set()

    for bundle in common_bundles:
        old_bundle = old_root / bundle
        new_bundle = new_root / bundle

        old_files = list_files(old_bundle)
        new_files = list_files(new_bundle)

        files_added = sorted(new_files - old_files)
        shared_files = sorted(old_files & new_files)

        files_changed: list[str] = []
        for rel_path in shared_files:
            old_file = old_bundle / rel_path
            new_file = new_bundle / rel_path
            if sha256sum(old_file) != sha256sum(new_file):
                files_changed.append(rel_path)

        bundle_new_key_paths: set[str] = set()
        plist_candidates = sorted(set(files_added) | set(files_changed))
        for rel_path in plist_candidates:
            old_file = old_bundle / rel_path
            new_file = new_bundle / rel_path

            old_plist = try_read_plist(old_file) if old_file.exists() else None
            new_plist = try_read_plist(new_file) if new_file.exists() else None

            if old_plist is None and new_plist is None:
                continue

            old_paths = flatten_schema(old_plist) if old_plist is not None else set()
            new_paths = flatten_schema(new_plist) if new_plist is not None else set()

            added_paths = sorted(new_paths - old_paths)

            for key_path in added_paths:
                bundle_new_key_paths.add(key_path)
                all_new_key_paths.add(key_path)

        if bundle_new_key_paths:
            new_tags_by_bundle.append(
                {
                    "bundle": bundle,
                    "new_key_paths": sorted(bundle_new_key_paths)[:max_key_entries],
                }
            )

    new_tags = sorted(all_new_key_paths)[:max_key_entries]
    total_new_keys = len(all_new_key_paths)

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "old_root": str(old_root),
        "new_root": str(new_root),
        "summary": {
            "new_carriers_detected": len(new_carriers),
            "new_keys_detected": total_new_keys,
        },
        "new_carriers": new_carriers,
        "new_tags_by_bundle": new_tags_by_bundle,
        "new_tags": new_tags,
    }
    return report


def build_carrier_report(bundles_dir: Path, carrier_a: str, carrier_b: str, max_key_entries: int) -> dict[str, Any]:
    dir_a = bundles_dir / carrier_a
    dir_b = bundles_dir / carrier_b

    files_a = list_files(dir_a)
    files_b = list_files(dir_b)

    files_only_in_a = sorted(files_a - files_b)
    files_only_in_b = sorted(files_b - files_a)
    shared_files = sorted(files_a & files_b)

    files_differing: list[str] = []
    for rel_path in shared_files:
        if sha256sum(dir_a / rel_path) != sha256sum(dir_b / rel_path):
            files_differing.append(rel_path)

    plist_diffs: list[dict[str, Any]] = []
    for rel_path in sorted(set(files_only_in_a) | set(files_only_in_b) | set(files_differing)):
        path_a = dir_a / rel_path
        path_b = dir_b / rel_path
        plist_a = try_read_plist(path_a) if path_a.exists() else None
        plist_b = try_read_plist(path_b) if path_b.exists() else None
        if plist_a is None and plist_b is None:
            continue
        keys_a = flatten_schema(plist_a) if plist_a is not None else set()
        keys_b = flatten_schema(plist_b) if plist_b is not None else set()
        only_a = sorted(keys_a - keys_b)
        only_b = sorted(keys_b - keys_a)
        if only_a or only_b:
            plist_diffs.append({
                "file": rel_path,
                "keys_only_in_a": only_a[:max_key_entries],
                "keys_only_in_b": only_b[:max_key_entries],
            })

    total_keys_a = sum(len(d["keys_only_in_a"]) for d in plist_diffs)
    total_keys_b = sum(len(d["keys_only_in_b"]) for d in plist_diffs)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "bundles_dir": str(bundles_dir),
        "carrier_a": carrier_a,
        "carrier_b": carrier_b,
        "summary": {
            "files_only_in_a": len(files_only_in_a),
            "files_only_in_b": len(files_only_in_b),
            "files_differing": len(files_differing),
            "plist_keys_only_in_a": total_keys_a,
            "plist_keys_only_in_b": total_keys_b,
        },
        "files_only_in_a": files_only_in_a,
        "files_only_in_b": files_only_in_b,
        "files_differing": files_differing,
        "plist_diffs": plist_diffs,
    }


def summarize_carrier_report(report: dict[str, Any]) -> str:
    s = report["summary"]
    a = report["carrier_a"]
    b = report["carrier_b"]
    lines: list[str] = []

    lines.append("## Summary")
    lines.append("| | Count |")
    lines.append("|---|---|")
    lines.append(f"| Files only in `{a}` | {s['files_only_in_a']} |")
    lines.append(f"| Files only in `{b}` | {s['files_only_in_b']} |")
    lines.append(f"| Files differing | {s['files_differing']} |")
    lines.append(f"| Plist keys only in `{a}` | {s['plist_keys_only_in_a']} |")
    lines.append(f"| Plist keys only in `{b}` | {s['plist_keys_only_in_b']} |")
    lines.append("")

    if report["files_only_in_a"]:
        lines.append(f"## Files only in `{a}`")
        for f in report["files_only_in_a"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report["files_only_in_b"]:
        lines.append(f"## Files only in `{b}`")
        for f in report["files_only_in_b"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report["files_differing"]:
        lines.append("## Files present in both but different")
        for f in report["files_differing"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if report["plist_diffs"]:
        lines.append("## Plist Key Differences")
        for diff in report["plist_diffs"]:
            lines.append(f"### `{diff['file']}`")
            if diff["keys_only_in_a"]:
                lines.append(f"**Keys only in `{a}`:**")
                for k in diff["keys_only_in_a"]:
                    lines.append(f"- `{k}`")
            if diff["keys_only_in_b"]:
                lines.append(f"**Keys only in `{b}`:**")
                for k in diff["keys_only_in_b"]:
                    lines.append(f"- `{k}`")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate carrier bundle change and key-diff reports")
    parser.add_argument("--old-dir", required=True, help="Path to previous Carrier Bundles directory")
    parser.add_argument("--new-dir", required=True, help="Path to current Carrier Bundles directory")
    parser.add_argument("--output-json", required=True, help="Path for JSON report output")
    parser.add_argument("--output-md", required=True, help="Path for Markdown report output")
    parser.add_argument(
        "--max-key-entries",
        type=int,
        default=1000,
        help="Maximum number of key entries to emit per report section",
    )
    return parser.parse_args()


def main() -> int:
    # compare-carriers subcommand — does not affect the original CLI
    if len(sys.argv) > 1 and sys.argv[1] == "compare-carriers":
        parser = argparse.ArgumentParser(
            prog="cb_change_report.py compare-carriers",
            description="Compare two carrier bundles side-by-side within the same version",
        )
        parser.add_argument("--bundles-dir", required=True, help="Path to Carrier Bundles directory")
        parser.add_argument("--carrier-a", required=True, help="First carrier bundle name (e.g. NOS_pt.bundle)")
        parser.add_argument("--carrier-b", required=True, help="Second carrier bundle name (e.g. Vodafone_pt.bundle)")
        parser.add_argument("--output-json", required=True, help="Path for JSON report output")
        parser.add_argument("--output-md", required=True, help="Path for Markdown report output")
        parser.add_argument("--max-key-entries", type=int, default=1000)
        args = parser.parse_args(sys.argv[2:])

        bundles_dir = Path(args.bundles_dir)
        output_json = Path(args.output_json)
        output_md = Path(args.output_md)

        if not bundles_dir.exists():
            raise FileNotFoundError(f"--bundles-dir does not exist: {bundles_dir}")
        for name in (args.carrier_a, args.carrier_b):
            if not (bundles_dir / name).exists():
                raise FileNotFoundError(f"Bundle not found: {bundles_dir / name}")

        report = build_carrier_report(bundles_dir, args.carrier_a, args.carrier_b, max_key_entries=args.max_key_entries)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        output_md.write_text(summarize_carrier_report(report), encoding="utf-8")
        print(json.dumps(report["summary"], indent=2))
        return 0

    # original version-compare mode — interface unchanged
    args = parse_args()
    old_dir = Path(args.old_dir)
    new_dir = Path(args.new_dir)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)

    if not old_dir.exists():
        raise FileNotFoundError(f"old-dir does not exist: {old_dir}")
    if not new_dir.exists():
        raise FileNotFoundError(f"new-dir does not exist: {new_dir}")

    report = build_report(old_dir, new_dir, max_key_entries=args.max_key_entries)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    output_md.write_text(summarize_report(report), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
