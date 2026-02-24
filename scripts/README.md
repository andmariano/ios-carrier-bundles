# Scripts

This directory contains automation scripts for carrier bundle analysis and reporting.

## generate_pt_changes.py

Generates a machine-readable JSON report of Portugal carrier bundle changes between two git commits.

### Purpose

This script extracts structured data about Portugal country and carrier bundle version changes, making it easy for automated systems to:
- Track carrier bundle versions over time
- Trigger automated testing when PT bundles change
- Generate notifications or alerts
- Feed data into monitoring dashboards
- Maintain historical change records

### Usage

```bash
# Compare HEAD with previous commit (HEAD~1)
python3 scripts/generate_pt_changes.py

# Compare specific commit with its parent
python3 scripts/generate_pt_changes.py 4be613bef

# Compare two specific commits
python3 scripts/generate_pt_changes.py HEAD 4be613bef~1

# Save to file
python3 scripts/generate_pt_changes.py > portugal_changes.json
```

### Output Format

The script outputs JSON with the following structure:

```json
{
  "report_generated": "2026-02-24T23:26:28.002381+00:00",
  "ios_version": "26.4",
  "ios_build": "23E5218e",
  "ios_release": "iOS 26.4 beta 2",
  "release_date": "2026-02-23",
  "commit_sha": "HEAD",
  "country": "Portugal",
  "country_code": "PT",
  "bundles_changed": [
    {
      "type": "country",
      "name": "Portugal",
      "bundle_id": "com.apple.Portugal",
      "version_old": "68.0",
      "version_new": "68.5",
      "files_modified": ["Info.plist", "signatures/common.plist"]
    },
    {
      "type": "carrier",
      "name": "Optimus",
      "bundle_id": "com.apple.Optimus_pt",
      "version_old": "68.0",
      "version_new": "68.5.2",
      "files_modified": ["Info.plist", "carrier.plist", ...]
    }
  ]
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `report_generated` | string | ISO 8601 timestamp of report generation (UTC) |
| `ios_version` | string | iOS version number (e.g., "26.4") |
| `ios_build` | string | iOS build identifier (e.g., "23E5218e") |
| `ios_release` | string | Human-readable iOS release name (e.g., "iOS 26.4 beta 2") |
| `release_date` | string | Date of iOS release (ISO 8601 date format) |
| `commit_sha` | string | Git commit SHA or reference used for comparison |
| `country` | string | Country name ("Portugal") |
| `country_code` | string | ISO country code ("PT") |
| `bundles_changed` | array | List of changed bundles |

### Bundle Object Schema

Each object in `bundles_changed` array:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Bundle type: "country" or "carrier" |
| `name` | string | Bundle name (e.g., "Portugal", "Optimus", "TMN") |
| `bundle_id` | string | Apple bundle identifier (e.g., "com.apple.Optimus_pt") |
| `version_old` | string | Previous version number |
| `version_new` | string | New version number |
| `files_modified` | array | List of modified files (only in git-based script) |

## generate_pt_changes_ci.py

CI-specific version that compares directory structures instead of git commits. Used by GitHub Actions workflow.

### Usage

```bash
python3 scripts/generate_pt_changes_ci.py <base_dir> <head_dir>

# Example (as used in CI)
python3 scripts/generate_pt_changes_ci.py /tmp/base-bundles /tmp/head-bundles > portugal-changes.json
```

### Differences from generate_pt_changes.py

- **Input:** Directory paths instead of git commits
- **Output:** Same JSON structure but without `files_modified` field
- **Use Case:** CI environments where bundles are extracted to temporary directories

### GitHub Actions Integration

The workflow `.github/workflows/carrier-bundle-change-alerts.yml` automatically:
1. Extracts carrier bundles from base and head iOS versions
2. Runs `generate_pt_changes_ci.py` to create JSON report
3. Embeds JSON in GitHub issue body (collapsible section)
4. Uploads JSON as workflow artifact (`reports/portugal-changes.json`)
5. Adds appropriate labels to the issue

### Consuming the JSON in Your Systems

#### Example: Python Script

```python
import json
import requests

# Fetch from GitHub issue or artifact
response = requests.get('https://example.com/portugal-changes.json')
data = response.json()

# Process changes
for bundle in data['bundles_changed']:
    if bundle['type'] == 'carrier':
        print(f"{bundle['name']}: {bundle['version_old']} → {bundle['version_new']}")
        
        # Trigger automated testing
        if bundle['version_old'] != bundle['version_new']:
            trigger_carrier_tests(bundle['name'], bundle['version_new'])
```

#### Example: Shell Script

```bash
#!/bin/bash
# Monitor for new iOS releases

ios_version=$(jq -r '.ios_version' portugal-changes.json)
ios_build=$(jq -r '.ios_build' portugal-changes.json)

echo "New iOS release detected: iOS ${ios_version} (${ios_build})"

# Check if bundles changed
bundle_count=$(jq '.bundles_changed | length' portugal-changes.json)

if [ "$bundle_count" -gt 0 ]; then
    echo "${bundle_count} Portugal bundles changed"
    
    # Send notification
    curl -X POST https://api.slack.com/webhooks/... \
        -d "{\"text\": \"Portugal carrier bundles updated in iOS ${ios_version}\"}"
fi
```

#### Example: JavaScript/Node.js

```javascript
const fs = require('fs');

const changes = JSON.parse(fs.readFileSync('portugal-changes.json', 'utf8'));

// Build notification message
const message = {
    ios: `${changes.ios_release} (${changes.ios_build})`,
    timestamp: changes.report_generated,
    bundles: changes.bundles_changed.map(b => ({
        name: b.name,
        type: b.type,
        versionChange: `${b.version_old} → ${b.version_new}`
    }))
};

console.log(JSON.stringify(message, null, 2));
```

## Notes

- Scripts require `plutil` (available on macOS by default)
- Git-based script requires repository with carrier bundle history
- CI script can work with any directory structure matching iOS bundle layout
- All timestamps are in UTC timezone
- Version comparison is string-based (not semantic versioning)
