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
The session ends two hours after setup starts, with a 125-minute job limit
to allow cleanup. This setup has been tested successfully from Windows,
including transferring and opening the preview DMG. A normal LAN connection
works; a phone hotspot is not required.
Normal branch commits and pushes do not start a session. Starting another
session cancels the previous one. It does not build software, publish releases,
or access the private source repository.

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
   For the default public servers, sign in under **Settings → Account → Login**
   using Google or GitHub. This account login is separate from the Mac's
   RustDesk connection password. Confirm the Windows client shows **Ready**.
   Under **Settings → Network → ID/Relay server**, leave **ID server**,
   **Relay server**, **API server** and **Key** blank, then click **OK**.
   Leave **Use WebSocket** off for this setup.

### Generate and save the passwords

Run the following in a local terminal with OpenSSL installed, such as WSL on
Windows. Each command prints a different random 32-character hexadecimal
password:

```sh
# Save this output as MAC_TEST_PASSWORD.
openssl rand -hex 16

# Save this separate output as MAC_TEST_ADMIN_PASSWORD.
openssl rand -hex 16
```

[`openssl rand`](https://docs.openssl.org/3.5/man1/openssl-rand/) generates
cryptographically secure random bytes; `-hex 16` encodes 16 bytes as 32
characters using only digits and lowercase a–f. This meets the setup's password
requirements and avoids punctuation that can be awkward to type through remote
keyboard layouts.

Save both outputs in a password manager and add their values as repository
secrets under **Settings → Secrets and variables → Actions → New repository
secret**. Enter the generated value, not the secret's name, when a password is
requested. GitHub does not display a secret's saved value later. Updating a
secret does not change the password on an already running Mac; start a new run
to use the new value.

| Credential | Where to use it |
| --- | --- |
| Google/GitHub account login | RustDesk on Windows: **Settings → Account → Login**. |
| `MAC_TEST_PASSWORD` value | RustDesk's remote password prompt after connecting to the Mac ID. |
| Username `mac-test-admin` and `MAC_TEST_ADMIN_PASSWORD` value | Administrator prompts inside the remote Mac. Replace the default username `runner`. |

### Launch from the test branch with a tag

After configuring the secrets, run these commands from this releases checkout:

```sh
git switch macos-test-desktop
git push origin macos-test-desktop
mac_test_tag="mac-desktop-test-$(date -u +%Y%m%d-%H%M%S)"
git tag "$mac_test_tag"
git push origin "refs/tags/$mac_test_tag"
```

The tag points to the current committed version, so commit your changes before
creating it. Push only the specific tag, rather than using `git push --tags`.
The timestamp generates a fresh tag name; do not reuse an existing tag.
The dedicated tag prefix does not create a GitHub Release or publish an installer.

Once the workflow has been merged into the default branch (`main`), you can also
use **Actions → macOS Test Desktop → Run workflow** and select a committed branch
from the branch dropdown. Until then, use the tag method above.

### Connect and test

1. Open **Actions** in the releases repository and select the run triggered by
   your tag (or the run you started with **Run workflow**).
2. Wait for **Start RustDesk test desktop** to complete. The run's summary and
   log show the RustDesk ID and UTC deadline. Use the summary for the current
   attempt if you reran the jobs. In Windows RustDesk, enter that ID and click
   **Connect**, then enter the value stored in `MAC_TEST_PASSWORD` when prompted.
3. Confirm that you can see Finder and use the keyboard and mouse. If access
   fails, cancel the run immediately. A registered ID does not prove that macOS
   screen/input permissions work. The setup stops if it cannot configure them.
4. Download the unpublished DMG artifact from the private source repository on
   Windows and extract the Actions ZIP. Try dragging the extracted DMG from
   Windows File Explorer into the remote window. If dragging does not work,
   use RustDesk's **File Transfer** option to copy it into the Mac's Downloads
   folder. No private-repository token is needed here.
5. Open the DMG, drag the app to Applications, eject the DMG, and launch the
   installed copy. Inspect menus, fonts, light/dark appearance, roster generation
   and XLSX export. If a system authentication prompt appears, enter username
   `mac-test-admin` and the password stored in `MAC_TEST_ADMIN_PASSWORD`.
   The desktop remains logged in as the runner user; its password is not reset.
   Finder usually hides the `.app` extension: the **HospitalRosterSystem** icon
   inside the DMG is the application. Open the copy in **Applications**, rather
   than the icon in the mounted **Hospital Roster System Test** volume. See the
   next section if macOS blocks opening it.
6. Cancel the workflow when finished, or open Terminal on the remote Mac and run
   `touch ~/Desktop/END-MAC-TEST` for a normal session exit.

Each run uses a disposable Mac. After the session ends, its installed app and
transferred files are lost. Launch a fresh run and transfer the DMG again; save
any test results back to Windows before ending the session.

### Open the preview app when macOS blocks it

The current preview is ad hoc signed and not notarized by Apple, so the
**Apple could not verify HospitalRosterSystem is free of malware** warning is
expected. Click **Done**, then open **System Settings → Privacy & Security**,
scroll to the blocked-app message, and select **Open Anyway**. If asked to
authenticate, enter username **`mac-test-admin`** and the value of
**`MAC_TEST_ADMIN_PASSWORD`**. See [Apple's instructions](https://support.apple.com/en-au/102445).

If that password works in Terminal but the approval dialog still rejects it,
or RustDesk will not let you paste into that dialog, use this workaround for
your own preview build on the disposable test Mac:

1. Cancel the approval dialog and close the warning with **Done**.
2. Make sure the app has been copied into **Applications**.
3. Open **Terminal on the remote Mac** and run:

   ```sh
   sudo -n xattr -dr com.apple.quarantine "/Applications/HospitalRosterSystem.app"
   open "/Applications/HospitalRosterSystem.app"
   ```

The runner supports passwordless `sudo`, so these commands do not require the
administrator password. They remove the download quarantine attribute from
this installed test copy and open it from Applications. This enables GUI
testing; it does not fix signing or notarization for distribution. Record the
original warning before using the workaround. If a command reports **No such
file**, check that the app was copied into Applications and that its filename
is `HospitalRosterSystem.app`.

To check the temporary administrator password independently, run this in the
Mac's Terminal:

```sh
dscl . -authonly mac-test-admin
```

Enter the `MAC_TEST_ADMIN_PASSWORD` value when prompted; no characters or dots
appear as you type. Returning to the prompt without an error means the password
was accepted. If it fails, check that you used the administrator secret rather
than the RustDesk connection secret, and the value used when this run started.

### Connection troubleshooting

- **Not ready. Please check your connection** on Windows: check that the server
  fields are blank, then fully quit and reopen RustDesk. If the problem persists,
  another network, such as a phone's mobile hotspot, can help diagnose LAN
  filtering. A hotspot is optional; normal LAN access has also worked.
- **The connection is not allowed** with a request to log in: sign into
  RustDesk under **Settings → Account → Login** using Google or GitHub, then
  reconnect. This happens before the remote password prompt. See the
  [public-server login guide](https://github.com/rustdesk/rustdesk/wiki/Login-required-for-public-server).
- **Target device is offline or does not exist**: check that the current job is
  still keeping the desktop available and use its latest summary's ID. IDs can
  remain the same across attempts, so the number alone does not prove that a
  session is current. Public-server or Mac network failures can still prevent
  connection even after setup succeeds.
- The RustDesk ID appears in this public repository's workflow summary and logs.
  Public visibility does not grant desktop access, but someone with the ID and
  connection password could connect to the same desktop. Keep the passwords
  private and cancel the session when testing is finished.

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
warning is expected. Record this check before removing quarantine using the
Terminal workaround above. To repeat the original Gatekeeper check afterwards,
use a fresh browser download and installed copy, preferably in a fresh session.
Do not disable Gatekeeper system-wide to make the test pass.

### Limits and implementation

- This is an experimental hosted-runner GUI setup, not a guaranteed remote Mac
  service. It fails early if there is no active Aqua session, the runner blocks
  RustDesk's permission setup, or the desktop service does not report an online
  connection and confirmed registration key. Setup reads the ID from the active
  desktop service; a stored ID alone is insufficient. This does not prove that
  the Windows client can reach the Mac or that screen/input access works.
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
