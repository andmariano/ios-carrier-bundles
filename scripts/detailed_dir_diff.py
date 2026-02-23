#!/usr/bin/env python3
import argparse
import difflib
import json
import plistlib
from pathlib import Path

PLIST_SUFFIXES = {".plist", ".mobileconfig"}


def list_relative_files(root: Path) -> set[str]:
    if not root.exists() or not root.is_dir():
        return set()
    paths: set[str] = set()
    for path in root.rglob("*"):
        if path.is_file():
            paths.add(str(path.relative_to(root)).replace("\\", "/"))
    return paths


def read_plist_as_text(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            value = plistlib.load(handle)
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    except Exception:
        return None


def read_text_or_none(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in PLIST_SUFFIXES:
        plist_text = read_plist_as_text(path)
        if plist_text is not None:
            return plist_text

    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def compare_dirs(base_dir: Path, head_dir: Path) -> str:
    all_files = sorted(list_relative_files(base_dir) | list_relative_files(head_dir))
    output_lines: list[str] = []

    for rel_path in all_files:
        base_file = base_dir / rel_path
        head_file = head_dir / rel_path

        if not base_file.exists():
            output_lines.append(f"Only in head: {rel_path}")
            continue
        if not head_file.exists():
            output_lines.append(f"Only in base: {rel_path}")
            continue

        base_bytes = base_file.read_bytes()
        head_bytes = head_file.read_bytes()
        if base_bytes == head_bytes:
            continue

        base_text = read_text_or_none(base_file)
        head_text = read_text_or_none(head_file)

        output_lines.append(f"Changed: {rel_path}")

        if base_text is None or head_text is None:
            output_lines.append(f"Binary files differ: {rel_path}")
            output_lines.append("")
            continue

        diff_lines = difflib.unified_diff(
            base_text.splitlines(),
            head_text.splitlines(),
            fromfile=f"base/{rel_path}",
            tofile=f"head/{rel_path}",
            lineterm="",
        )
        output_lines.extend(diff_lines)
        output_lines.append("")

    return "\n".join(output_lines).rstrip() + ("\n" if output_lines else "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit detailed, value-level diffs between two directories")
    parser.add_argument("--base-dir", required=True, help="Base directory")
    parser.add_argument("--head-dir", required=True, help="Head directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir)
    head_dir = Path(args.head_dir)

    if not base_dir.exists() and not head_dir.exists():
        print("")
        return 0

    text = compare_dirs(base_dir, head_dir)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
