
# iOS Carrier Bundles

Automated collection of iOS Carrier Bundles extracted directly from the latest iOS IPSW releases.

> **Compatibility Note:** This repository tracks carrier bundles starting with iOS 26+. Bundles may work on older iOS versions, but compatibility is not guaranteed.

---

## Latest Extraction

| | |
|---|---|
| **Extracted at** | `(CURRENT_DATE)` |
| **iOS Version** | (IOS_VERSION) |
| **iOS Build** | (IOS_BUILD) |
| **Build Timestamp** | (IOS_BUILD_TIMESTAMP) |
| **Device** | (DEVICE_NAME) (`(DEVICE_PRODNAME)`) |

---

## Workflows

### 🔄 Update Carrier Bundles

Runs **automatically once daily at 05:00 UTC**. Can also be triggered manually.

- Checks if a new iOS build (stable or beta) is available for the target device
- Only downloads and extracts when a new build is detected — skips otherwise
- After a successful update, automatically triggers the **Carrier Bundle Change Alerts** workflow

**Manual inputs:**

| Input | Default | Description |
|---|---|---|
| `device` | `iPhone18,3` | iOS device identifier |
| `include_beta` | `true` | Include beta/RC releases in latest build check |

---

### 🔔 Carrier Bundle Change Alerts

Triggered automatically after each bundle update, or manually for custom version comparisons.
Generates a diff report and opens a **GitHub Issue**.

**Manual inputs for custom version compare:**

| Input | Description |
|---|---|
| `base_version` | iOS version for the base snapshot |
| `head_version` | iOS version for the head snapshot |
| `base_build` | Optional exact build for base (beta/RC targeting) |
| `head_build` | Optional exact build for head (beta/RC targeting) |
| `base_ref` / `head_ref` | Git ref or commit SHA fallback |
| `include_beta` | Include beta/RC releases (`true` by default) |

> Input priority: `build` > `version` > `ref`

**Every report issue includes:**

| Section | Content |
|---|---|
| 📊 Quick Summary | Version change table for all affected bundles |
| 🌍 Portugal Country Bundle | Value-level diff for `Country Bundles/Portugal.bundle` |
| 📡 Portugal Carrier Bundles | Value-level diffs for all `Carrier Bundles/*_pt.bundle` |
| 🔑 New Plist Keys | Newly detected keys across all carrier bundles |
| 🤖 Machine-Readable JSON | Portugal changes in JSON format (collapsible) |

**Auto-applied labels:** `carrier-bundles` · `automated-report` · `ios-{version}` · `beta4` / `beta3` / ... _(beta releases, numbered)_ · `stable` _(stable releases)_

---

### 🔀 Compare Carrier Bundles — Between Carriers

Manually triggered. Compares two carrier bundles side-by-side within the same iOS version and opens a **GitHub Issue**.

**Inputs:**

| Input | Default | Description |
|---|---|---|
| `git_ref` | `main` | Branch, tag, or SHA to read bundles from |
| `carrier_a` | — | First carrier bundle name |
| `carrier_b` | — | Second carrier bundle name |

**The issue includes:**

- Files present only in carrier A or only in carrier B
- Files present in both but with different content
- Plist key differences per file

---

## Machine-Readable Portugal Changes

Every change report generates `reports/portugal-changes.json` with structured data:

- iOS version and build
- Bundle types (country/carrier) with version changes
- Bundle identifiers and names
- Report timestamp

**Access methods:**
1. **GitHub Issues** — JSON embedded in issue body (collapsible)
2. **Workflow Artifacts** — download `carrier-bundle-change-report`
3. **Local script** — `python3 scripts/generate_pt_changes.py` (see [scripts/README.md](scripts/README.md))

---

## Folder Structure

### `Carrier Bundles/`

Carrier-specific bundles. iOS filesystem path:
```
/System/Library/Carrier Bundles/iPhone/
```

### `Country Bundles/`

Bundles that apply to all carriers within a country. iOS filesystem path:
```
/System/Library/CountryBundles/iPhone/
```

All files are in Apple's binary plist format. Further reading: [The Apple Wiki — Carrier Bundles](https://theapplewiki.com/wiki/Carrier_Bundle).

---

## Acknowledgements

- [blacktop/ipsw](https://github.com/blacktop/ipsw)
- [sgan81/apfs-fuse](https://github.com/sgan81/apfs-fuse)
