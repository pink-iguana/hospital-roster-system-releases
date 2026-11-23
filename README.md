# Hospital Roster System releases

[Download the latest stable release](https://github.com/pink-iguana/hospital-roster-system-releases/releases/latest)
or [browse all releases](https://github.com/pink-iguana/hospital-roster-system-releases/releases).

## Install or update

| Platform | Installer | How to install |
| --- | --- | --- |
| Windows x64 | `HospitalRosterSystem-<version>-windows-x64.msi` | Open the MSI, follow the prompts, and launch **Hospital Roster System** from the Start menu. |
| Apple Silicon, macOS 15 or later | `HospitalRosterSystem-<version>-macos-arm64.dmg` | Open the DMG, drag **HospitalRosterSystem** into **Applications**, eject the disk image, and launch the installed copy. |

Quit the app before updating and keep your `.rosterproj` files outside the
installation folder. In the current app, **File → View Latest Release** opens
the stable download page. Windows installers are unsigned. The macOS app uses
ad hoc signing and carries no Apple notarization. Follow your organisation's
installation policy when your operating system displays a warning.

## Guide, licences, and checksums

- **`HospitalRosterSystem-User-Guide.pdf`** covers the editor, roster generation,
  Excel export, and command-line use. The same PDF is installed with the app.
- **`HospitalRosterSystem-BINARY-USE-LICENCE.txt`** contains the terms of use.
  Use requires prior written approval from either owner. Their contact
  details are in the licence.
- **`SHA256SUMS.txt`** lists the SHA-256 fingerprints for the uploaded files.
  The platform candidate receipts record the source and build details, and the
  notice indexes list the third-party dependencies. Full notices are installed
  with the app.

## Earlier Qt releases

The [v3.4.5 release notes](https://github.com/pink-iguana/hospital-roster-system-releases/releases/tag/v3.4.5)
cover the legacy Qt installers, their licence bundle, and the
[corresponding Qt source](https://github.com/pink-iguana/hospital-roster-system-releases/releases/tag/qt-6.7.3-source-3).

<details>
<summary>Historical Qt compliance workflow</summary>

Under **Actions → Verify Qt compliance → Run workflow**, choose Windows, macOS
or both. Set both tag inputs explicitly to the legacy application and the
corresponding Qt source named in its release notes. For example, use
`v3.4.5` with `qt-6.7.3-source-3`. A source that differs from the installed
app's source URL or checksum is rejected.

The workflow installs/copies the actual public installer, checks its hashes,
notices, licence texts, recipient-rights clauses and corresponding source. It
builds Qt with a small `qVersion()` marker patch in an isolated Conan home,
replaces deployed Qt libraries/plugins in a copy of the app, and verifies actual
loaded paths/hashes, the marker, GUI startup and Preferences/Roster tab switching.
Windows uses the MSI's normal installation; macOS copies the app from its DMG,
preserves loader paths and re-signs the modified copy ad hoc. Original application
code and the private Validator payload are checked for preservation.

Runs use standard public `windows-2022` and Apple Silicon `macos-15` runners.
They require no repository secrets, private source access or distributor signing
key. The macOS runner grants only its signed GUI helper Accessibility access;
it does not disable Gatekeeper or change SIP. Conan 2.30.0, Python 3.12 and the
recorded native toolchain are required. An unavailable recorded Xcode/compiler
fails explicitly. Each platform has a 350-minute limit; Qt builds may take hours.
There are no persistent build caches and no automatic branch-push runs.

Download the seven-day `qt-compliance-<platform>-<run-id>` evidence artifact for
stage results, source/release identities, patch, build/toolchain logs, signing
checks and loaded libraries. A failed GUI check is a failure, not a manual pass.
Stages that never ran are labelled `not_run`. Setup failures remain visible in
the Actions summary/logs. No modified packages or release assets are published.

This is focused technical evidence for Qt distribution and replacement. It does
not automate roster calculations/Excel export, assess comprehensive legal
compliance, or establish browser quarantine/Gatekeeper behaviour on consumer
machines. The macOS application remains ad hoc signed and not notarized.

Local lightweight checks: `python scripts/check_qt_compliance.py` and actionlint.

</details>

## Contact

For questions about releases or distribution, [open an issue](https://github.com/pink-iguana/hospital-roster-system-releases/issues).
