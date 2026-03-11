#!/usr/bin/env python3
"""
iOS Carrier Bundle DB Ingestor
==============================
Reads iOS carrier bundle change data from:
  - Local report files (CI mode, called after each workflow run)
  - GitHub Issues (historical backfill via GitHub API)

Writes structured records to a PostgreSQL database (see db_schema.sql).

Usage
-----
  # First-time setup – create tables:
  python db_parser/ingest_to_db.py --mode local --init-schema

  # CI mode – ingest current build after a workflow run:
  python db_parser/ingest_to_db.py --mode local \\
      --metadata ipsw_metadata.json \\
      --pt-changes portugal_changes.json \\
      --cb-report  reports/cb-change-report.json

  # Historical backfill – pull all issues from GitHub:
  python db_parser/ingest_to_db.py --mode github-issues \\
      --repo andmariano/ios-carrier-bundles

  # Query all iOS releases recorded:
  python db_parser/ingest_to_db.py --mode query-ios

  # Show change history for a specific carrier bundle:
  python db_parser/ingest_to_db.py --mode query-carrier --bundle NOS_pt.bundle -v

  # Show Portugal bundle history (all bundles or one):
  python db_parser/ingest_to_db.py --mode query-pt
  python db_parser/ingest_to_db.py --mode query-pt --bundle Vodafone

Environment variables (DB connection)
--------------------------------------
  DB_HOST        PostgreSQL host          (default: localhost)
  DB_PORT        PostgreSQL port          (default: 5432)
  DB_NAME        Database name            (default: carrier_bundles)
  DB_USER        Database user            (default: postgres)
  DB_PASSWORD    Database password        *** required ***
  GITHUB_TOKEN   Personal access token   (required for github-issues mode)
  GITHUB_REPOSITORY  owner/repo          (default: andmariano/ios-carrier-bundles)
"""

import argparse
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
    import requests
except ImportError:
    sys.exit(
        "[ERROR] Missing dependencies.\n"
        "Install with: pip install psycopg2-binary requests"
    )


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def db_connect() -> "psycopg2.connection":
    password = os.environ.get("DB_PASSWORD")
    if not password:
        sys.exit("[ERROR] DB_PASSWORD environment variable is required.")
    try:
        return psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ.get("DB_NAME", "carrier_bundles"),
            user=os.environ.get("DB_USER", "postgres"),
            password=password,
        )
    except psycopg2.OperationalError as exc:
        sys.exit(f"[ERROR] Cannot connect to database: {exc}")


def apply_schema(conn: Any, schema_path: Path) -> None:
    with schema_path.open(encoding="utf-8") as fh:
        ddl = fh.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print(f"[SCHEMA] Schema applied from {schema_path}")


# ---------------------------------------------------------------------------
# DB write helpers – all queries fully parameterised (no injection risk)
# ---------------------------------------------------------------------------

def upsert_ios_release(
    cur: Any,
    version: str,
    build: str,
    is_beta: bool,
    full_label: str,
    os_type: str,
    release_date: Any,
) -> None:
    cur.execute(
        """
        INSERT INTO ios_releases
            (version, build, is_beta, full_version_label, os_type, release_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (build) DO UPDATE SET
            full_version_label = EXCLUDED.full_version_label,
            is_beta            = EXCLUDED.is_beta,
            os_type            = EXCLUDED.os_type,
            release_date       = COALESCE(EXCLUDED.release_date, ios_releases.release_date)
        """,
        (version, build, is_beta, full_label, os_type, release_date),
    )


def upsert_devices(cur: Any, ios_build: str, devices: list[dict]) -> None:
    for dev in devices:
        ts = _parse_ipsw_ts(dev.get("timestamp"))
        cur.execute(
            """
            INSERT INTO ios_devices
                (ios_build, device_name, product_id, board, build_timestamp, cpu_info)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ios_build, product_id) DO UPDATE SET
                device_name     = EXCLUDED.device_name,
                board           = EXCLUDED.board,
                build_timestamp = EXCLUDED.build_timestamp,
                cpu_info        = EXCLUDED.cpu_info
            """,
            (
                ios_build,
                dev.get("name"),
                dev.get("product"),
                dev.get("board"),
                ts,
                dev.get("cpu"),
            ),
        )


def insert_bundle_key_changes(
    cur: Any, ios_build: str, new_tags_by_bundle: list[dict]
) -> None:
    for item in new_tags_by_bundle:
        bundle = item.get("bundle", "")
        for key_path in item.get("new_key_paths", []):
            cur.execute(
                """
                INSERT INTO carrier_bundle_key_changes (ios_build, bundle_name, key_path)
                VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                """,
                (ios_build, bundle, key_path),
            )


def upsert_pt_changes(cur: Any, pt_data: dict) -> None:
    ios_build    = pt_data.get("ios_build", "")
    ios_version  = pt_data.get("ios_version", "")
    ios_release  = pt_data.get("ios_release", "")
    release_date = _parse_date(pt_data.get("release_date"))

    for bundle in pt_data.get("bundles_changed", []):
        bundle_id = bundle.get("bundle_id") or ""
        if not ios_build or not bundle_id:
            continue  # skip records without unique identifiers

        cur.execute(
            """
            INSERT INTO pt_bundle_changes (
                ios_build, ios_version, ios_release, release_date,
                bundle_type, bundle_name, bundle_id, version_old, version_new
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ios_build, bundle_id) DO UPDATE SET
                version_old  = EXCLUDED.version_old,
                version_new  = EXCLUDED.version_new,
                release_date = COALESCE(EXCLUDED.release_date, pt_bundle_changes.release_date)
            RETURNING id
            """,
            (
                ios_build,
                ios_version,
                ios_release,
                release_date,
                bundle.get("type"),
                bundle.get("name"),
                bundle_id,
                bundle.get("version_old"),
                bundle.get("version_new"),
            ),
        )
        row = cur.fetchone()
        if not row:
            continue
        pt_change_id = row[0]

        for file_path in bundle.get("files_modified", []):
            cur.execute(
                """
                INSERT INTO pt_bundle_file_changes (pt_change_id, file_path)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (pt_change_id, file_path),
            )


# ---------------------------------------------------------------------------
# Utility / parsing helpers
# ---------------------------------------------------------------------------

def _parse_ipsw_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%d %b %Y %H:%M:%S UTC").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _parse_date(date_str: str | None):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_metadata(meta: dict) -> dict:
    """Normalise fields from ipsw_metadata.json."""
    version  = meta.get("version", "unknown")
    build    = meta.get("build", "unknown")
    os_type  = (meta.get("os") or "").strip()
    is_beta  = os_type.lower() not in ("", "release", "gm", "stable")

    full_label = f"iOS {version}"
    if is_beta and os_type:
        full_label += f" {os_type}"

    devices = meta.get("devices", [])
    release_date = None
    if devices:
        ts = _parse_ipsw_ts(devices[0].get("timestamp"))
        release_date = ts.date() if ts else None

    return dict(
        version=version,
        build=build,
        is_beta=is_beta,
        full_label=full_label,
        os_type=os_type,
        release_date=release_date,
        devices=devices,
    )


# ---------------------------------------------------------------------------
# Mode: local – ingest from files on disk
# ---------------------------------------------------------------------------

def ingest_local(conn: Any, args: argparse.Namespace) -> None:
    metadata_path = Path(args.metadata)
    pt_path       = Path(args.pt_changes)
    cb_path       = Path(args.cb_report)

    if not metadata_path.exists():
        sys.exit(f"[ERROR] Metadata file not found: {metadata_path}")

    with metadata_path.open(encoding="utf-8") as fh:
        info = _extract_metadata(json.load(fh))

    pt_data: dict = {}
    if pt_path.exists():
        with pt_path.open(encoding="utf-8") as fh:
            pt_data = json.load(fh)
    else:
        print(f"[WARN] PT changes file not found: {pt_path} – skipping PT data")

    cb_report: dict = {}
    if cb_path.exists():
        with cb_path.open(encoding="utf-8") as fh:
            cb_report = json.load(fh)
    else:
        print(f"[WARN] CB report not found: {cb_path} – carrier key changes will be empty")

    with conn.cursor() as cur:
        upsert_ios_release(
            cur,
            info["version"],
            info["build"],
            info["is_beta"],
            info["full_label"],
            info["os_type"],
            info["release_date"],
        )
        upsert_devices(cur, info["build"], info["devices"])

        if cb_report.get("new_tags_by_bundle"):
            insert_bundle_key_changes(cur, info["build"], cb_report["new_tags_by_bundle"])

        if pt_data.get("bundles_changed"):
            upsert_pt_changes(cur, pt_data)

    conn.commit()
    print(f"[OK] {info['full_label']} ({info['build']})")
    print(f"     Devices: {len(info['devices'])}")
    if pt_data.get("bundles_changed"):
        print(f"     PT bundles: {len(pt_data['bundles_changed'])}")
    if cb_report.get("new_tags_by_bundle"):
        print(f"     Bundles with new keys: {len(cb_report['new_tags_by_bundle'])}")


# ---------------------------------------------------------------------------
# Mode: github-issues – backfill from GitHub Issues + workflow artifacts
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(
    r"iOS\s+([\d.]+)\s*(beta\s*\d+|beta|RC|GM|Release)?\s*\(([A-Za-z0-9]+)\)",
    re.IGNORECASE,
)
_JSON_BLOCK_RE = re.compile(r"```json\s*\n([\s\S]*?)\n```")
_RUN_URL_RE    = re.compile(
    r"https://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+/actions/runs/(\d+)"
)


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _gh_get(url: str, token: str, params: dict | None = None) -> Any:
    r = requests.get(url, headers=_gh_headers(token), params=params, timeout=30)
    r.raise_for_status()
    return r


def _fetch_issues(repo: str, label: str, token: str) -> list[dict]:
    url    = f"https://api.github.com/repos/{repo}/issues"
    params: dict = {"labels": label, "state": "all", "per_page": 100}
    items: list[dict] = []
    while url:
        r = _gh_get(url, token, params)
        items.extend(r.json())
        url    = r.links.get("next", {}).get("url")  # type: ignore[assignment]
        params = {}
    return items


def _fetch_artifact_cb_report(repo: str, run_id: str, token: str) -> dict | None:
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts"
    try:
        r = _gh_get(url, token)
    except requests.HTTPError:
        return None
    for artifact in r.json().get("artifacts", []):
        if artifact.get("name") == "carrier-bundle-change-report":
            dl_url = artifact["archive_download_url"]
            dl = requests.get(
                dl_url, headers=_gh_headers(token), timeout=120, allow_redirects=True
            )
            if dl.status_code != 200:
                return None
            try:
                with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
                    for name in zf.namelist():
                        if name.endswith("cb-change-report.json"):
                            return json.loads(zf.read(name))
            except (zipfile.BadZipFile, json.JSONDecodeError):
                return None
    return None


def _extract_pt_json_from_body(body: str) -> dict | None:
    """Parse the embedded JSON block from the 🤖 Machine-Readable Format section."""
    marker = "## \U0001f916 Machine-Readable Format"
    if marker not in body:
        return None
    section = body.split(marker, 1)[1][:8192]
    for m in _JSON_BLOCK_RE.finditer(section):
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "bundles_changed" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _parse_issue_title(title: str) -> dict | None:
    m = _TITLE_RE.search(title)
    if not m:
        return None
    version   = m.group(1).strip()
    qualifier = (m.group(2) or "").strip()
    build     = m.group(3).strip()
    is_beta   = "beta" in qualifier.lower()

    full_label = f"iOS {version}"
    if qualifier:
        full_label += f" {qualifier}"

    return dict(version=version, build=build, is_beta=is_beta, full_label=full_label)


def ingest_github_issues(conn: Any, args: argparse.Namespace) -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("[ERROR] GITHUB_TOKEN environment variable is required.")

    repo = args.repo
    if not repo:
        sys.exit("[ERROR] --repo is required for github-issues mode.")

    issues = _fetch_issues(repo, "carrier-bundles", token)
    print(f"[INFO] Found {len(issues)} issues with label 'carrier-bundles'")

    for issue in issues:
        number = issue.get("number")
        title  = issue.get("title", "")
        body   = issue.get("body") or ""

        parsed = _parse_issue_title(title)
        if not parsed:
            print(f"  [SKIP] #{number}: cannot parse title: {title!r}")
            continue

        run_id  = (m := _RUN_URL_RE.search(body)) and m.group(1)
        pt_data: dict = _extract_pt_json_from_body(body) or {}

        cb_report: dict = {}
        if run_id:
            print(f"  [FETCH] #{number}: artifact for run {run_id} …", end=" ", flush=True)
            cb_report = _fetch_artifact_cb_report(repo, run_id, token) or {}
            print("ok" if cb_report else "not available (expired or no artifact)")

        release_date = _parse_date(pt_data.get("release_date"))

        with conn.cursor() as cur:
            upsert_ios_release(
                cur,
                parsed["version"],
                parsed["build"],
                parsed["is_beta"],
                parsed["full_label"],
                "beta" if parsed["is_beta"] else "Release",
                release_date,
            )

            if cb_report.get("new_tags_by_bundle"):
                insert_bundle_key_changes(cur, parsed["build"], cb_report["new_tags_by_bundle"])
            if pt_data.get("bundles_changed"):
                upsert_pt_changes(cur, pt_data)

        conn.commit()
        print(f"  [OK] #{number}: {parsed['full_label']} ({parsed['build']})")


# ---------------------------------------------------------------------------
# Query modes
# ---------------------------------------------------------------------------

def query_carrier(conn: Any, args: argparse.Namespace) -> None:
    """Show change history for a specific carrier bundle."""
    bundle = args.bundle
    if not bundle:
        sys.exit("[ERROR] --bundle is required for query-carrier mode.")

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT
                r.full_version_label  AS ios_version,
                r.build,
                r.release_date,
                r.is_beta,
                COUNT(k.id)           AS new_keys
            FROM carrier_bundle_key_changes k
            JOIN ios_releases r ON r.build = k.ios_build
            WHERE k.bundle_name = %s
            GROUP BY r.full_version_label, r.build, r.release_date, r.is_beta
            ORDER BY r.release_date DESC NULLS LAST
            """,
            (bundle,),
        )
        rows = cur.fetchall()

    if not rows:
        print(f"No change records found for bundle: {bundle}")
        return

    print(f"\nCarrier bundle history: {bundle}")
    print(f"{'iOS Version':<30} {'Build':<15} {'Date':<12} {'New Keys':>9}")
    print("─" * 68)
    for row in rows:
        print(
            f"{row['ios_version'] or '?':<30} {row['build']:<15} "
            f"{str(row['release_date'] or '?'):<12} {row['new_keys']:>9}"
        )
    print(f"\nTotal iOS versions with changes: {len(rows)}")

    if args.verbose:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT r.full_version_label, r.build, k.key_path
                FROM   carrier_bundle_key_changes k
                JOIN   ios_releases r ON r.build = k.ios_build
                WHERE  k.bundle_name = %s
                ORDER  BY r.release_date DESC NULLS LAST, k.key_path
                """,
                (bundle,),
            )
            key_rows = cur.fetchall()

        print(f"\nAll new plist keys for: {bundle}")
        print("─" * 68)
        cur_build = None
        for row in key_rows:
            if row["build"] != cur_build:
                cur_build = row["build"]
                print(f"\n  [{row['full_version_label']} / {row['build']}]")
            print(f"    {row['key_path']}")


def query_pt(conn: Any, args: argparse.Namespace) -> None:
    """Show Portugal / country bundle history."""
    bundle_filter = getattr(args, "bundle", None)
    where  = "WHERE p.bundle_name = %s" if bundle_filter else ""
    params = [bundle_filter] if bundle_filter else []

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            f"""
            SELECT
                r.full_version_label  AS ios_version,
                p.ios_build,
                p.ios_release,
                p.release_date,
                r.is_beta,
                p.bundle_type,
                p.bundle_name,
                p.bundle_id,
                p.version_old,
                p.version_new,
                ARRAY(
                    SELECT f.file_path
                    FROM   pt_bundle_file_changes f
                    WHERE  f.pt_change_id = p.id
                    ORDER  BY f.file_path
                ) AS files_modified
            FROM pt_bundle_changes p
            LEFT JOIN ios_releases r ON r.build = p.ios_build
            {where}
            ORDER BY p.release_date DESC NULLS LAST, p.bundle_type, p.bundle_name
            """,
            params,
        )
        rows = cur.fetchall()

    if not rows:
        print("No Portugal bundle records found.")
        return

    print(
        f"\n{'iOS Release':<28} {'Build':<15} {'Type':<8} "
        f"{'Bundle':<22} {'Version'}"
    )
    print("─" * 90)
    for row in rows:
        verchg = f"{row['version_old']} → {row['version_new']}"
        print(
            f"{row['ios_release'] or '?':<28} {row['ios_build']:<15} "
            f"{row['bundle_type'] or '?':<8} {row['bundle_name']:<22} {verchg}"
        )
        for fp in row["files_modified"]:
            print(f"    ↳ {fp}")


def query_ios(conn: Any, _args: argparse.Namespace) -> None:
    """Show all iOS releases in the database."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT
                r.full_version_label,
                r.build,
                r.os_type,
                r.is_beta,
                r.release_date,
                r.ingested_at,
                COUNT(DISTINCT d.id) AS device_count,
                COUNT(DISTINCT k.id) AS total_new_keys
            FROM ios_releases r
            LEFT JOIN ios_devices                d ON d.ios_build = r.build
            LEFT JOIN carrier_bundle_key_changes k ON k.ios_build = r.build
            GROUP BY
                r.id, r.full_version_label, r.build, r.os_type, r.is_beta,
                r.release_date, r.ingested_at
            ORDER BY r.release_date DESC NULLS LAST, r.ingested_at DESC
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No iOS releases in database.")
        return

    print(
        f"\n{'iOS Version':<30} {'Build':<15} {'OS Type':<14} "
        f"{'Date':<12} {'Beta':>4} {'Dev':>3} {'New Keys':>9}"
    )
    print("─" * 90)
    for row in rows:
        beta_str = "✓" if row["is_beta"] else ""
        print(
            f"{row['full_version_label'] or '?':<30} {row['build']:<15} "
            f"{row['os_type'] or '':<14} {str(row['release_date'] or '?'):<12} "
            f"{beta_str:>4} {row['device_count']:>3} {row['total_new_keys']:>9}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="iOS Carrier Bundle DB Ingestor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--mode",
        choices=["local", "github-issues", "query-ios", "query-carrier", "query-pt"],
        required=True,
        metavar="MODE",
        help=(
            "local          – ingest from local report files\n"
            "github-issues  – backfill from GitHub Issues + artifacts\n"
            "query-ios      – list all iOS releases in DB\n"
            "query-carrier  – carrier bundle change history (--bundle required)\n"
            "query-pt       – Portugal bundle history"
        ),
    )
    p.add_argument(
        "--init-schema",
        action="store_true",
        help="Create/update DB tables before running (safe – uses IF NOT EXISTS).",
    )
    p.add_argument(
        "--schema",
        default=str(Path(__file__).parent / "db_schema.sql"),
        help="Path to db_schema.sql",
    )

    # local mode
    p.add_argument("--metadata",   default="ipsw_metadata.json",
                   help="Path to ipsw_metadata.json")
    p.add_argument("--pt-changes", default="portugal_changes.json",
                   help="Path to portugal_changes.json")
    p.add_argument("--cb-report",  default="reports/cb-change-report.json",
                   help="Path to cb-change-report.json")

    # github-issues mode
    p.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "andmariano/ios-carrier-bundles"),
        help="GitHub repository owner/name",
    )

    # query modes
    p.add_argument("--bundle", help="Bundle name filter (e.g. NOS_pt.bundle)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    conn = db_connect()

    try:
        if args.init_schema or args.mode in ("local", "github-issues"):
            schema_path = Path(args.schema)
            if schema_path.exists():
                apply_schema(conn, schema_path)
            elif args.init_schema:
                sys.exit(f"[ERROR] Schema file not found: {schema_path}")

        if args.mode == "local":
            ingest_local(conn, args)
        elif args.mode == "github-issues":
            ingest_github_issues(conn, args)
        elif args.mode == "query-ios":
            query_ios(conn, args)
        elif args.mode == "query-carrier":
            query_carrier(conn, args)
        elif args.mode == "query-pt":
            query_pt(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
