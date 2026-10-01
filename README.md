Hospital Roster System — Releases

Purpose
-------
This repository hosts published binary releases (installers) for the Westmead Hospital Roster System. It contains release assets (MSI installers) and release notes created by the main repository CI.

How artifacts are published
--------------------------
- The main repository CI builds artifacts (Windows MSI via WiX) and uses the GitHub CLI to create releases in this repository.

Artifact naming convention
-------------------------
- Windows MSI: `HospitalRosterSystem-<version>-windows-x64.msi` (e.g. `HospitalRosterSystem-1.2.3-windows-x64.msi`).
- User guide: `HospitalRosterSystem-User-Guide.pdf`.
- Binary-use licence: `HospitalRosterSystem-BINARY-USE-LICENCE.txt`.
- Licence bundle: `HospitalRosterSystem-Licences.zip`.

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

Manual macOS installer testing from Windows
-------------------------------------------
The **macOS Test Desktop** workflow starts a temporary macOS 15 Apple Silicon
desktop for testing Hospital Roster System through RustDesk on Windows. It is
started explicitly by a `mac-desktop-*` tag push or the **Run workflow** button.
It has a 30-minute job limit and ends around 25 minutes after setup starts.
Normal branch commits and pushes do not start a session. Starting another session cancels the previous one. It does not build
software, publish releases, or access the private source repository.

### One-time setup

1. Review, commit and push the workflow, script and README on `macos-test-desktop`.
   The tag launch below works while they remain on that branch; merging into
   `main` is not required for tag launches.
2. Under **Settings → Secrets and variables → Actions**, add:
   - `MAC_TEST_PASSWORD`: the RustDesk connection password.
   - `MAC_TEST_ADMIN_PASSWORD`: the password for temporary administrator `mac-test-admin`.
   Use separate, unique 16–128 character printable ASCII passwords. Passwords
   are never intentionally logged or uploaded as artifacts. Rotate them after
   testing; do not reuse personal account passwords.
3. Install the official Windows RustDesk client from
   [RustDesk](https://rustdesk.com/download).

### Launch from the test branch with a tag

After configuring the secrets, run these commands from this releases checkout:

```sh
git switch macos-test-desktop
git push origin macos-test-desktop
git tag mac-desktop-test-001
git push origin mac-desktop-test-001
```

The tag points to the current committed version, so commit your changes before
creating it. Push only the specific tag, rather than using `git push --tags`.
Use a new name for each new session, such as `mac-desktop-test-002`.
The dedicated tag prefix does not create a GitHub Release or publish an installer.

Once the workflow has been merged into the default branch (`main`), you can also
use **Actions → macOS Test Desktop → Run workflow** and select a committed branch
from the branch dropdown. Until then, use the tag method above.

### Connect and test

1. Open **Actions** in the releases repository and select the run triggered by
   your tag (or the run you started with **Run workflow**).
2. Wait for **Start RustDesk test desktop** to complete. The run's summary and
   log show the RustDesk ID and UTC deadline. Connect from Windows with that ID
   and the password you stored in `MAC_TEST_PASSWORD`.
3. Confirm that you can see Finder and use the keyboard and mouse. If access
   fails, cancel the run immediately. A registered ID does not prove that macOS
   screen/input permissions work. The setup stops if it cannot configure them.
4. Download the unpublished DMG artifact from the private source repository on
   Windows, extract the Actions ZIP, and transfer the DMG through RustDesk to
   the Mac's Downloads folder. No private-repository token is needed here.
5. Open the DMG, drag the app to Applications, eject the DMG, and launch the
   installed copy. Inspect menus, fonts, light/dark appearance, roster generation
   and XLSX export. If a system authentication prompt appears, enter username
   `mac-test-admin` and the password stored in `MAC_TEST_ADMIN_PASSWORD`.
   The desktop remains logged in as the runner user; its password is not reset.
6. Cancel the workflow when finished, or open Terminal on the remote Mac and run
   `touch ~/Desktop/END-MAC-TEST` for a normal session exit.

### Browser-download and Gatekeeper check

RustDesk file transfer may not set the download quarantine attribute. To test a
browser download before publication, put the DMG in `~/Downloads/preview`, then
run this command in the remote Mac's Terminal:

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory "$HOME/Downloads/preview"
```

Open `http://127.0.0.1:8080/` in Safari and download the DMG to a fresh location.
Check `xattr -p com.apple.quarantine /path/to/downloaded.dmg` before drawing
conclusions about Gatekeeper. Stop the local server with Ctrl+C. The current
preview is ad hoc signed and not notarized, so an unsigned/unidentified-developer
warning is expected. Do not disable Gatekeeper to make the test pass.

### Limits and implementation

- This is an experimental hosted-runner GUI setup, not a guaranteed remote Mac
  service. It fails early if there is no active Aqua session or the runner blocks
  RustDesk's permission setup. Native connection is unverified until the first run.
- The script pins RustDesk 1.4.9 and verifies its published asset SHA-256 and app
  signature. It installs launchd services following the pinned RustDesk source.
- To bootstrap remote access, it writes permission records only for the installed
  RustDesk app, using its actual bundle ID and signing requirement. The macOS
  privacy database is an internal interface and may change with runner updates.
  SIP and Gatekeeper are not disabled. The app being tested receives no grants.
- Runner images contain development tools. Retain the build pipeline's dependency
  audit; this desktop is primarily for installation and GUI acceptance. An M1
  session tests ARM64 compatibility, but does not establish M4-specific behaviour.
- Standard runners in this public repository are free, subject to
  [GitHub Actions terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions).
  Use the session only to develop/test this repository's associated software,
  with one licensed user at a time. No auto-chaining, VPN rotation or general
  desktop hosting is configured.
- Cancel/timeout destroys the disposable runner. Cleanup stops the RustDesk
  services when GitHub allows the cleanup step to run. Never upload credentials,
  RustDesk configuration, or the private test installer as a workflow artifact.
