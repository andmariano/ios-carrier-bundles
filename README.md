
# iOS 26.4 Carrier Bundles

This repo contains the Carrier Bundles currently bundled with iOS version 26.4 for the iPhone 17.

> **Compatibility Note:** This repository tracks carrier bundles starting with iOS 26. Carrier bundles from iOS 26+ may work on older iOS versions, but compatibility is not guaranteed and feature parity may vary.
## Last Extraction Metadata

#### Last Extraction Time
`2026-02-24 00:16:34 UTC`

#### iOS Build Info

| iOS Version | iOS Build | iOS Build Timestamp |
| :-------- | :------- | :------------------ |
| 26.4 | 23E5218e | 16 Feb 2026 04:56:29 UTC |

#### iOS Device Info

| Device Name | Device Identifier |
| :-------- | :------- |
| iPhone 17 | iPhone18,3 |

## Workflow Device Selection

The GitHub Actions workflow supports manual inputs when you run `Update Carrier Bundles`.

- Default device: iPhone 17 Pro Max (`iPhone18,3`)
- Override: Actions → `Update Carrier Bundles` → `Run workflow` → set `device`
- If no input is provided, workflow uses the default `iPhone18,3`
- `include_beta` defaults to `true` (set `false` for stable-only latest build checks); if the installed `ipsw` does not support `--beta`, workflow resolves latest beta build via `ipsw.me` (and falls back to `ipsw.dev`) and downloads by build ID

## Automation + Alerts

This repo includes two GitHub Actions workflows for automation:

- `Update Carrier Bundles`: checks every 12 hours (and manually) and only downloads/extracts when a new iOS build is detected
- `Carrier Bundle Change Alerts`: runs on bundle updates, generates a diff report, and opens a GitHub issue with machine-readable JSON for Portugal changes

### Custom Compare (example: iOS 26.0 → 26.3)

Use `Carrier Bundle Change Alerts` with `Run workflow` and set:

- `base_version`: iOS version for base snapshot (example: `26.0`)
- `head_version`: iOS version for head snapshot (example: `26.3`)
- `base_build`: optional base build for exact beta/RC targeting (example: `23E5222f`)
- `head_build`: optional head build for exact beta/RC targeting (example: `23E5230a`)
- `include_beta`: defaults to `true` (set `false` for stable-only lookup); if `--beta` is unsupported by installed `ipsw`, workflow resolves latest beta build via `ipsw.me` with `ipsw.dev` fallback
- Optional fallback: `base_ref` / `head_ref` for git refs or commit SHAs

When `base_build`/`head_build` are set, build targeting takes priority for download lookup.
When `base_version`/`head_version` are set, they take priority over refs.
If version inputs are empty, `base_ref`/`head_ref` are used.
If a ref is not found, the workflow automatically treats that value as an iOS version and downloads it for comparison.

### What Gets Reported

- Across all folders in `Carrier Bundles/*.bundle`, monitoring is only for:
	- New carrier bundles
	- Newly introduced plist `key_path` options (schema/key presence only)
- Dedicated alert when `Country Bundles/Portugal.bundle` changes
- Dedicated alert when any carrier bundle matching `Carrier Bundles/*_pt.bundle` changes

Each time the report workflow runs on a bundle update, it opens a new issue with:

- **Quick Summary Table:** Visual overview of version changes for country and carrier bundles
- **Machine-Readable JSON:** Parsable Portugal changes in JSON format (collapsible)
- Detailed value-level diffs for `Country Bundles/Portugal.bundle`
- Detailed value-level diffs for `Carrier Bundles/*_pt.bundle`
- A flat `## Newly Detected Plist Keys` list (`key_path` only, deduplicated)
- A `## Full report artifact` section with links to full files including `portugal-changes.json`
- **Labels:** Automatic issue tagging with `carrier-bundles`, `automated-report`, `portugal`, `pt-carriers`, `ios-{version}`, and `beta` (when applicable)

### Machine-Readable Portugal Changes

For automated processing of Portugal carrier bundle changes, the workflow generates `reports/portugal-changes.json` with structured data including:

- iOS version and build information
- Bundle types (country/carrier) with version changes
- Bundle identifiers and names
- Timestamp of report generation

**Access methods:**
1. **GitHub Issues:** JSON embedded in issue body (collapsible section)
2. **Workflow Artifacts:** Download `carrier-bundle-change-report` artifact
3. **Local Script:** Run `python3 scripts/generate_pt_changes.py` (see [scripts/README.md](scripts/README.md))

**Example use cases:**
- Automated monitoring systems
- Version tracking databases
- CI/CD integration for carrier testing
- Historical change analysis

See [scripts/README.md](scripts/README.md) for detailed usage and JSON schema.

## Folder Explanations

#### Carrier Bundles
This folder contains the Carrier Bundles specific to each carrier.

On the iOS filesystem, this folder can be found at:
```
/System/Library/Carrier Bundles/iPhone
```

These files are in Apple's binary plist format, so you will need an editor that can handle these kinds of files to view them.

[The Apple Wiki](https://theapplewiki.com/) has further information on [Carrier Bundles](https://theapplewiki.com/wiki/Carrier_Bundle).

#### Country Bundles
This folder contains the Carrier Bundles that apply to all carriers within a country.

On the iOS filesystem, this folder can be found at:
```
/System/Library/CountryBundles/iPhone/
```

These files are in Apple's binary plist format, so you will need an editor that can handle these kinds of files to view them.

## Acknowledgements
 - [blacktop/ipsw](https://github.com/blacktop/ipsw)
 - [sgan81/apfs-fuse](https://github.com/sgan81/apfs-fuse)