"""Native macOS desktop, signing, replacement and loaded-image checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import subprocess
import time

IDENTITY = 'org.pinkiguana.qt-compliance-gui'


def setup(work):
    evidence = work / 'evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    helper = work / 'QtComplianceGUI.app/Contents'
    (helper / 'MacOS').mkdir(parents=True, exist_ok=True)
    with (helper / 'Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleIdentifier': IDENTITY, 'CFBundleExecutable': 'QtComplianceGUI',
                      'CFBundleName': 'Qt Compliance GUI', 'CFBundlePackageType': 'APPL',
                      'CFBundleVersion': '1'}, stream)
    subprocess.run(['xcrun', 'swiftc', str(Path(__file__).with_name('qt_compliance_gui.swift')),
                    '-o', str(helper / 'MacOS/QtComplianceGUI')], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(helper.parent)], check=True)
    result = subprocess.run(['codesign', '-d', '-r-', str(helper.parent)],
                            text=True, capture_output=True, check=True)
    signing = result.stdout + result.stderr
    (evidence / 'gui-helper-signature.txt').write_text(signing)
    match = re.search(r'designated => (.+)', signing)
    if not match:
        raise RuntimeError('No designated requirement for GUI helper')
    requirement = work / 'gui-helper.csreq'
    subprocess.run(['csreq', '-r', '= ' + match[1], '-b', str(requirement)], check=True)
    subprocess.run(['sudo', 'python3', str(Path(__file__).resolve()), 'permissions',
                    '--work', str(work)], check=True)
    subprocess.run(['sudo', 'killall', 'tccd'], check=False)
    # Permission is granted only to this signed helper in the disposable runner.
    subprocess.run([str(helper / 'MacOS/QtComplianceGUI'), 'preflight'], check=True)
    (evidence / 'desktop-setup.json').write_text(json.dumps({'helper': IDENTITY,
                                               'permission': 'Accessibility'}, indent=2))


def permissions(work):
    if os.geteuid() != 0:
        raise RuntimeError('Permission setup requires sudo on the disposable runner')
    database = '/Library/Application Support/com.apple.TCC/TCC.db'
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute('''INSERT OR REPLACE INTO access
            (service, client, client_type, auth_value, auth_reason, auth_version,
             csreq, policy_id, indirect_object_identifier_type,
             indirect_object_identifier, indirect_object_code_identity, flags, last_modified)
            VALUES (?, ?, 0, 2, 4, 1, ?, NULL, 0, 'UNUSED', NULL, 0, ?)''',
            ('kTCCServiceAccessibility', IDENTITY,
             (work / 'gui-helper.csreq').read_bytes(), int(time.time())))


def preflight(work):
    user = subprocess.check_output(['stat', '-f', '%Su', '/dev/console'], text=True).strip()
    current = subprocess.check_output(['id', '-un'], text=True).strip()
    if user != current or user in ('root', 'loginwindow'):
        raise RuntimeError('macOS runner has no active desktop for the current user')
    subprocess.run([str(work / 'QtComplianceGUI.app/Contents/MacOS/QtComplianceGUI'),
                    'preflight'], check=True)


def install(installer, work, run):
    mount = work / 'mounted'
    run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(installer)])
    app = work / 'installed/HospitalRosterSystem.app'
    try:
        app.parent.mkdir(exist_ok=True)
        run(['ditto', str(mount / 'HospitalRosterSystem.app'), str(app)])
    finally:
        run(['hdiutil', 'detach', str(mount)])
    run(['codesign', '--verify', '--deep', '--strict', str(app)])
    return app


def executable(app):
    return app / 'Contents/MacOS/HospitalRosterSystem'


def licences(app):
    return app / 'Contents/Resources/Licences'


def gui(process, evidence, label):
    helper = evidence.parent / 'QtComplianceGUI.app/Contents/MacOS/QtComplianceGUI'
    result = subprocess.run([str(helper), str(process.pid)], text=True,
                            capture_output=True, timeout=150)
    (evidence / f'{label}-gui.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'macOS GUI interaction failed: {result.stderr.strip()}')
    json.loads(result.stdout)
    result = subprocess.run(['vmmap', '-w', str(process.pid)], text=True,
                            capture_output=True, check=True, timeout=60)
    (evidence / f'{label}-vmmap.txt').write_text(result.stdout)
    paths = set()
    for line in result.stdout.splitlines():
        match = re.search(r'\s(/.*(?:libQt6[^/]*\.dylib|libqcocoa\.dylib))\s*$', line)
        if match:
            paths.add(match[1])
    return sorted(paths)


def text_code(path, run):
    # codesign changes signature data, not the application instructions.
    return '\n'.join(run(['otool', '-s', '__TEXT', '__text', str(path)]).splitlines()[1:])


def replace(app, package, run):
    frameworks = app / 'Contents/Frameworks'
    changed = []
    for old in frameworks.glob('libQt6*.dylib'):
        source = package / 'lib' / old.name
        if not source.is_file():
            raise RuntimeError(f'Rebuilt Qt lacks {old.name}')
        shutil.copyfile(source, old)
        changed.append(old)
    for old in (app / 'Contents/PlugIns').rglob('*.dylib'):
        relative = old.relative_to(app / 'Contents/PlugIns')
        source = package / 'plugins' / relative
        if not source.is_file():
            raise RuntimeError(f'Rebuilt Qt lacks plugin {relative}')
        shutil.copyfile(source, old)
        changed.append(old)
    for path in changed:
        output = run(['otool', '-L', str(path)])
        references = [line.strip().split(' (compatibility')[0]
                      for line in output.splitlines()[1:]]
        edits = []
        for reference in references:
            name = Path(reference).name
            if name.startswith('libQt6') and (frameworks / name).is_file():
                relative = os.path.relpath(frameworks / name, path.parent)
                edits += ['-change', reference, '@loader_path/' + relative]
            elif reference.startswith('/') and not reference.startswith(('/usr/lib/', '/System/Library/')):
                raise RuntimeError(f'Unexpected non-system absolute Qt import: {reference}')
        if path.parent == frameworks:
            edits += ['-id', '@rpath/' + path.name]
        if edits:
            run(['install_name_tool', *edits, str(path)])
        rpaths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset',
                            run(['otool', '-l', str(path)]))
        for rpath in dict.fromkeys(rpaths):
            if rpath.startswith('/') and not rpath.startswith(('/usr/lib', '/System/Library')):
                run(['install_name_tool', '-delete_rpath', rpath, str(path)])
        run(['codesign', '--force', '--sign', '-', str(path)])
    run(['codesign', '--force', '--sign', '-', str(app)])
    run(['codesign', '--verify', '--deep', '--strict', str(app)])


def probe(app, package, work, run):
    source = work / 'version-probe.cpp'
    source.write_text('#include <QtCore/QtGlobal>\n#include <cstdio>\n'
                      'int main(){std::puts(qVersion());}\n')
    library = app / 'Contents/Frameworks/libQt6Core.6.dylib'
    output = work / 'version-probe'
    run(['xcrun', 'clang++', '-std=c++17', '-DQT_CORE_LIB', '-I' + str(package / 'include'),
         str(source), str(library), '-Wl,-rpath,' + str(library.parent), '-o', str(output)])
    run(['codesign', '--force', '--sign', '-', str(output)])
    return run([str(output)]).strip()


def cleanup(installer, run):
    pass  # Copies live only in the disposable runner; DMG is already detached.


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('setup', 'permissions'))
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    globals()[args.command](args.work.resolve())
