Hospital Roster System — Releases

Purpose
-------
This repository hosts Windows MSI and Apple Silicon macOS DMG releases for
Hospital Roster System, their documentation/licences and Qt corresponding source.

How artifacts are published
--------------------------
- The private source repository builds both installers and publishes verified
  assets here. The public verification workflow below consumes those releases.

Artifact naming convention
-------------------------
- Windows MSI: `HospitalRosterSystem-<version>-windows-x64.msi` (e.g. `HospitalRosterSystem-1.2.3-windows-x64.msi`).
- macOS DMG: `HospitalRosterSystem-<version>-macos-arm64.dmg`.
- User guide: `HospitalRosterSystem-User-Guide.pdf`.
- Binary-use licence: `HospitalRosterSystem-BINARY-USE-LICENCE.txt`.
- Licence bundle: `HospitalRosterSystem-Licences.zip`.
- Checksums: `SHA256SUMS.txt`.

Qt compliance verification
--------------------------
Under **Actions → Verify Qt compliance → Run workflow**, choose Windows, macOS
or both (the default). Leave the tag inputs empty for the newest published
application, including betas, and newest published Qt source. Set explicit tags
to reproduce an earlier pair. A source that differs from the installed app's
source URL/checksum is rejected, even if it is newer.

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

Licensing
---------
Hospital Roster System is proprietary software. Use requires prior written
approval from either owner. The applicable terms are provided in the binary-use
licence included with new releases.

- Shehzad Hathi: shehzadhathi@outlook.com
- Durga Chandran: durgachandran@gmail.com

Contact
-------------------
For questions about releases or distribution policy, raise an issue in this repository.
