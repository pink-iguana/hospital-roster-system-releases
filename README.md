Hospital Roster System — Releases

Purpose
-------
This repository hosts published binary releases (installers) for the Hospital Roster System. It contains release assets (MSI installers) and release notes created by the main repository CI.

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

Branch note
-----------
The `macos-test-desktop` branch includes the Python scripts and GitHub Actions
workflow for temporary macOS installer testing. Setup and usage instructions
for the testing environment are maintained in the main repository.
