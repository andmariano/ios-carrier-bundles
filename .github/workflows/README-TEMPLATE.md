
# iOS (IOS_VERSION) Carrier Bundles

This repo contains the Carrier Bundles currently bundled with iOS version (IOS_VERSION) for the (DEVICE_NAME).
## Last Extraction Metadata

#### Last Extraction Time
`(CURRENT_DATE)`

#### iOS Build Info

| iOS Version | iOS Build | iOS Build Timestamp |
| :-------- | :------- | :------------------ |
| (IOS_VERSION) | (IOS_BUILD) | (IOS_BUILD_TIMESTAMP) |

#### iOS Device Info

| Device Name | Device Identifier |
| :-------- | :------- |
| (DEVICE_NAME) | (DEVICE_PRODNAME) |

## Workflow Device Selection

The GitHub Actions workflow supports a manual `device` input when you run `Update Carrier Bundles`.

- Default device: iPhone 17 Pro Max (`iPhone18,3`)
- Override: Actions → `Update Carrier Bundles` → `Run workflow` → set `device`
- Fallback: if no input is provided, the workflow uses repository variable `DEVICE`

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