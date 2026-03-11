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

# Two-letter ISO country code → Country Bundle stem name
_CC_TO_COUNTRY: dict[str, str] = {
    "pt": "Portugal",
    "us": "UnitedStates",
    "gb": "UnitedKingdom",
    "de": "Germany",
    "fr": "France",
    "es": "Spain",
    "it": "Italy",
    "br": "Brazil",
    "au": "Australia",
    "ca": "Canada",
    "nl": "Netherlands",
    "be": "Belgium",
    "ch": "Switzerland",
    "at": "Austria",
    "se": "Sweden",
    "no": "Norway",
    "dk": "Denmark",
    "fi": "Finland",
    "pl": "Poland",
    "cz": "CzechRepublic",
    "ro": "Romania",
    "hu": "Hungary",
    "gr": "Greece",
    "tr": "Turkey",
    "za": "SouthAfrica",
    "in": "India",
    "cn": "China",
    "jp": "Japan",
    "kr": "Korea",
    "sg": "Singapore",
    "hk": "HongKong",
    "mx": "Mexico",
    "ar": "Argentina",
    "cl": "Chile",
    "co": "Colombia",
    "nz": "NewZealand",
    "ie": "Ireland",
    "il": "Israel",
    "ae": "UAE",
    "sa": "SaudiArabia",
}


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


def extract_scalar_leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    """Return {key_path: scalar_value} for all non-array leaf values."""
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            child_prefix = f"{prefix}.{k}" if prefix else str(k)
            result.update(extract_scalar_leaves(v, child_prefix))
    elif isinstance(value, list):
        pass  # skip arrays — paths are ambiguous when multiple items share the same key
    else:
        if prefix:
            result[prefix] = value
    return result


def _format_val(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, bytes):
        return f"<bytes {len(v)}B>"
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    return str(v)


def _detect_country_code(bundle_name: str) -> str | None:
    """Extract 2-letter country code from bundle name, e.g. 'Optimus_pt.bundle' → 'pt'."""
    stem = bundle_name.removesuffix(".bundle")
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isalpha():
        return parts[1].lower()
    return None


def _find_country_bundle(country_code: str, country_bundles_dir: Path) -> str | None:
    """Locate a country bundle directory for the given 2-letter ISO code."""
    # Try exact mapping first (case-insensitive bundle stem)
    candidate_stem = _CC_TO_COUNTRY.get(country_code.lower())
    if candidate_stem:
        candidate = f"{candidate_stem}.bundle"
        if (country_bundles_dir / candidate).exists():
            return candidate
    # Fallback: scan for any bundle whose stem contains the code
    for entry in sorted(country_bundles_dir.iterdir()):
        if entry.is_dir() and entry.name.endswith(".bundle"):
            if country_code.lower() in entry.name.lower():
                return entry.name
    return None


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


def build_carrier_report(
    bundles_dir: Path,
    carrier_a: str,
    carrier_b: str,
    max_key_entries: int,
    country_bundles_dir: Path | None = None,
) -> dict[str, Any]:
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
        only_a = sorted(keys_a - keys_b)[:max_key_entries]
        only_b = sorted(keys_b - keys_a)[:max_key_entries]

        # Value-level diff for shared scalar keys
        vals_a = extract_scalar_leaves(plist_a) if plist_a is not None else {}
        vals_b = extract_scalar_leaves(plist_b) if plist_b is not None else {}
        values_changed: list[dict[str, str]] = []
        for k in sorted(set(vals_a) & set(vals_b)):
            if vals_a[k] != vals_b[k]:
                values_changed.append({
                    "key": k,
                    "value_a": _format_val(vals_a[k]),
                    "value_b": _format_val(vals_b[k]),
                })
        values_changed = values_changed[:max_key_entries]

        if only_a or only_b or values_changed:
            plist_diffs.append({
                "file": rel_path,
                "keys_only_in_a": only_a,
                "keys_only_in_b": only_b,
                "values_changed": values_changed,
            })

    total_keys_a = sum(len(d["keys_only_in_a"]) for d in plist_diffs)
    total_keys_b = sum(len(d["keys_only_in_b"]) for d in plist_diffs)
    total_values_changed = sum(len(d["values_changed"]) for d in plist_diffs)

    # Country bundle section — auto-detected when both carriers share the same country code
    country_section: dict[str, Any] | None = None
    if country_bundles_dir is not None and country_bundles_dir.exists():
        code_a = _detect_country_code(carrier_a)
        code_b = _detect_country_code(carrier_b)
        if code_a and code_a == code_b:
            bundle_name = _find_country_bundle(code_a, country_bundles_dir)
            if bundle_name:
                country_section = _build_country_section(
                    country_bundles_dir / bundle_name, bundle_name, max_key_entries
                )

    result: dict[str, Any] = {
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
            "plist_values_changed": total_values_changed,
        },
        "files_only_in_a": files_only_in_a,
        "files_only_in_b": files_only_in_b,
        "files_differing": files_differing,
        "plist_diffs": plist_diffs,
    }
    if country_section is not None:
        result["country_bundle"] = country_section
    return result


def _build_country_section(
    bundle_dir: Path, bundle_name: str, max_key_entries: int
) -> dict[str, Any]:
    """Return a structured snapshot of all plist files in a country bundle directory."""
    plists: list[dict[str, Any]] = []
    for plist_file in sorted(bundle_dir.rglob("*.plist")):
        rel = str(plist_file.relative_to(bundle_dir)).replace("\\", "/")
        data = try_read_plist(plist_file)
        if data is None:
            continue
        scalars = extract_scalar_leaves(data)
        plists.append({
            "file": rel,
            "values": {k: _format_val(v) for k, v in sorted(scalars.items())[:max_key_entries]},
        })
    return {"bundle": bundle_name, "plists": plists}


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
    lines.append(f"| Plist values changed | {s.get('plist_values_changed', 0)} |")
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

    if report["plist_diffs"]:
        lines.append("## 🔍 Plist Differences")
        for diff in report["plist_diffs"]:
            lines.append(f"### `{diff['file']}`")

            if diff.get("values_changed"):
                lines.append(f"**Changed values:**")
                lines.append("")
                lines.append("| Key | `" + a + "` | `" + b + "` |")
                lines.append("|---|---|---|")
                for entry in diff["values_changed"]:
                    key = entry["key"].replace("|", "\\|")
                    va = entry["value_a"].replace("|", "\\|")
                    vb = entry["value_b"].replace("|", "\\|")
                    lines.append(f"| `{key}` | `{va}` | `{vb}` |")
                lines.append("")

            if diff["keys_only_in_a"]:
                lines.append(f"**Keys only in `{a}`:**")
                for k in diff["keys_only_in_a"]:
                    lines.append(f"- `{k}`")
                lines.append("")

            if diff["keys_only_in_b"]:
                lines.append(f"**Keys only in `{b}`:**")
                for k in diff["keys_only_in_b"]:
                    lines.append(f"- `{k}`")
                lines.append("")

    if "country_bundle" in report:
        cb = report["country_bundle"]
        lines.append(f"## 🌍 Country Bundle: `{cb['bundle']}`")
        lines.append("")
        lines.append("_Shared configuration that applies to both carriers at the country level._")
        lines.append("")
        for plist_entry in cb["plists"]:
            if not plist_entry["values"]:
                continue
            lines.append(f"### `{plist_entry['file']}`")
            lines.append("")
            lines.append("| Key | Value |")
            lines.append("|---|---|")
            for k, v in plist_entry["values"].items():
                k_esc = k.replace("|", "\\|")
                v_esc = str(v).replace("|", "\\|")
                lines.append(f"| `{k_esc}` | `{v_esc}` |")
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
        parser.add_argument("--carrier-a", required=True, help="First carrier bundle name")
        parser.add_argument("--carrier-b", required=True, help="Second carrier bundle name")
        parser.add_argument("--output-json", required=True, help="Path for JSON report output")
        parser.add_argument("--output-md", required=True, help="Path for Markdown report output")
        parser.add_argument("--max-key-entries", type=int, default=1000)
        parser.add_argument(
            "--country-bundles-dir",
            default=None,
            help="Path to Country Bundles directory; when provided, auto-includes the shared country bundle section",
        )
        args = parser.parse_args(sys.argv[2:])

        bundles_dir = Path(args.bundles_dir)
        output_json = Path(args.output_json)
        output_md = Path(args.output_md)
        country_bundles_dir = Path(args.country_bundles_dir) if args.country_bundles_dir else None

        if not bundles_dir.exists():
            raise FileNotFoundError(f"--bundles-dir does not exist: {bundles_dir}")
        for name in (args.carrier_a, args.carrier_b):
            if not (bundles_dir / name).exists():
                raise FileNotFoundError(f"Bundle not found: {bundles_dir / name}")

        report = build_carrier_report(
            bundles_dir,
            args.carrier_a,
            args.carrier_b,
            max_key_entries=args.max_key_entries,
            country_bundles_dir=country_bundles_dir,
        )
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
