
# iOS 26.3 Carrier Bundles

This repo contains the Carrier Bundles currently bundled with iOS version 26.3 for the iPhone 17.
## Last Extraction Metadata

#### Last Extraction Time
`2026-02-23 20:57:42 UTC`

#### iOS Build Info

| iOS Version | iOS Build | iOS Build Timestamp |
| :-------- | :------- | :------------------ |
| 26.3 | 23D127 | 28 Jan 2026 05:05:59 UTC |

#### iOS Device Info

| Device Name | Device Identifier |
| :-------- | :------- |
| iPhone 17 | iPhone18,3 |

## Workflow Device Selection

The GitHub Actions workflow supports a manual `device` input when you run `Update Carrier Bundles`.

- Default device: iPhone 17 Pro Max (`iPhone18,3`)
- Override: Actions → `Update Carrier Bundles` → `Run workflow` → set `device`
- If no input is provided, workflow uses the default `iPhone18,3`

## Automation + Alerts

This repo includes two GitHub Actions workflows for automation:

- `Update Carrier Bundles`: runs every 6 hours and can also be run manually
- `Carrier Bundle Change Alerts`: runs on bundle updates, generates a diff report, and opens a GitHub issue

### What Gets Reported

- Across all folders in `Carrier Bundles/*.bundle`, monitoring is only for:
	- New carrier bundles
	- Newly detected plist key paths ("new tags")
- Dedicated alert when `Country Bundles/Portugal.bundle` changes
- Dedicated alert when any carrier bundle matching `Carrier Bundles/*_pt.bundle` changes

### Private Repo + Email Notifications

Yes, this can run fully on GitHub (no n8n required):

1. Set the repository visibility to private in GitHub Settings.
2. In your GitHub notification settings, enable email notifications.
3. Watch this repository and include `Issues` in custom watch settings.

Each time the report workflow runs on a bundle update, it opens a new issue with:

- A human-readable markdown change report
- The full raw JSON report in a collapsible section
- Commit and workflow run links for traceability

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