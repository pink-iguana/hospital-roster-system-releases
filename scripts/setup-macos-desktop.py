#!/usr/bin/env python3
"""Set up a bounded installer QA session on a disposable GitHub macOS runner."""

import datetime
import hashlib
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import subprocess
import sys
import time


VERSION = '1.4.9'
ARCHIVE_SHA256 = 'f7935597b247d42c8f2a2ed71176a9f5868018cd9e1a33b8096418a668c8caf0'
APP = Path('/Applications/RustDesk.app')
DAEMON_LABEL = 'com.carriez.RustDesk_service'
AGENT_LABEL = 'com.carriez.RustDesk_server'


def run(*args, private=False, check=True, timeout=60):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True,
                            timeout=timeout)
    if check and result.returncode:
        detail = '' if private else ': ' + result.stderr.strip()
        raise RuntimeError(f'{Path(str(args[0])).name} failed{detail}')
    return result


def grant_permissions(bundle_id, requirement_file):
    # The runner is disposable. Grant only RustDesk's capture/input services;
    # do not change SIP, Gatekeeper or the application's permissions.
    database = Path('/Library/Application Support/com.apple.TCC/TCC.db')
    if not database.is_file():
        raise RuntimeError('Runner has no system privacy database')
    services = ('kTCCServiceAccessibility', 'kTCCServiceScreenCapture',
                'kTCCServiceListenEvent')
    with sqlite3.connect(str(database), timeout=10) as connection:
        for service in services:
            connection.execute('''INSERT OR REPLACE INTO access
                (service, client, client_type, auth_value, auth_reason,
                 auth_version, csreq, policy_id, indirect_object_identifier_type,
                 indirect_object_identifier, indirect_object_code_identity,
                 flags, last_modified)
                VALUES (?, ?, 0, 2, 4, 1, ?, NULL, 0, 'UNUSED', NULL, 0, ?)''',
                (service, bundle_id, Path(requirement_file).read_bytes(), int(time.time())))
        for service in services:
            row = connection.execute(
                'SELECT auth_value FROM access WHERE service=? AND client=? AND client_type=0',
                (service, bundle_id)).fetchone()
            if row != (2,):
                raise RuntimeError('RustDesk privacy permission was not stored')


def write_plist(path, data):
    temporary = Path(os.environ['RUNNER_TEMP']) / path.name
    temporary.write_bytes(plistlib.dumps(data))
    run('sudo', 'install', '-o', 'root', '-g', 'wheel', '-m', '644', temporary, path)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Run this setup only on a disposable GitHub Actions runner')
    if run('uname', '-s').stdout.strip() != 'Darwin' or run('uname', '-m').stdout.strip() != 'arm64':
        raise RuntimeError('This workflow requires an Apple Silicon macOS runner')
    secrets = {}
    for name in ('MAC_TEST_PASSWORD', 'MAC_TEST_ADMIN_PASSWORD'):
        value = os.environ.get(name, '')
        if not 16 <= len(value) <= 128 or not all(32 <= ord(c) <= 126 for c in value):
            raise RuntimeError(f'Set {name} to a unique 16–128 character printable ASCII secret')
        secrets[name] = value
    console_user = run('stat', '-f', '%Su', '/dev/console').stdout.strip()
    current_user = run('id', '-un').stdout.strip()
    uid = run('id', '-u').stdout.strip()
    if console_user != current_user or console_user in ('root', 'loginwindow'):
        raise RuntimeError('Runner has no active desktop for the current user')
    run('launchctl', 'print', f'gui/{uid}')
    run('sudo', 'dscl', '.', '-passwd', f'/Users/{console_user}',
        secrets['MAC_TEST_ADMIN_PASSWORD'], private=True)

    temporary = Path(os.environ['RUNNER_TEMP'])
    archive = temporary / 'rustdesk.dmg'
    url = f'https://github.com/rustdesk/rustdesk/releases/download/{VERSION}/rustdesk-{VERSION}-aarch64.dmg'
    print(f'Installing checksum-pinned RustDesk {VERSION}', flush=True)
    run('curl', '--fail', '--location', '--retry', '3', '--proto', '=https',
        '--proto-redir', '=https', url, '--output', archive, timeout=180)
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != ARCHIVE_SHA256:
            raise RuntimeError('RustDesk download checksum mismatch')
    mount = temporary / 'rustdesk-mounted'
    mount.mkdir()
    run('hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, archive)
    try:
        run('ditto', mount / 'RustDesk.app', APP)
    finally:
        run('hdiutil', 'detach', mount)
    run('codesign', '--verify', '--deep', '--strict', APP)
    info = plistlib.loads((APP / 'Contents/Info.plist').read_bytes())
    bundle_id = info['CFBundleIdentifier']
    executable = APP / 'Contents/MacOS' / info['CFBundleExecutable']
    service = APP / 'Contents/MacOS/service'
    if not executable.is_file() or not service.is_file():
        raise RuntimeError('Pinned RustDesk app is missing its executable or service')
    requirement = run('codesign', '-d', '-r-', APP).stderr
    match = re.search(r'^designated => (.+)$', requirement, re.MULTILINE)
    if not match:
        raise RuntimeError('Could not read RustDesk code-signing requirement')
    requirement_file = temporary / 'rustdesk.csreq'
    run('csreq', '-r', '= ' + match.group(1), '-b', requirement_file)
    result = run('sudo', sys.executable, Path(__file__).resolve(), '--grant-permissions',
                 bundle_id, requirement_file, check=False)
    if result.returncode:
        raise RuntimeError('Runner blocked RustDesk privacy setup. See the setup log; '
                           'the session cannot safely bootstrap screen/input access. ' + result.stderr.strip())
    run('sudo', 'killall', 'tccd', check=False)

    # Mirrors RustDesk 1.4.9's launchd service definitions, with the executable
    # read from the signed app rather than assuming its capitalization.
    daemon = Path('/Library/LaunchDaemons') / (DAEMON_LABEL + '.plist')
    agent = Path('/Library/LaunchAgents') / (AGENT_LABEL + '.plist')
    common = {'RunAtLoad': True, 'WorkingDirectory': str(executable.parent),
              'AssociatedBundleIdentifiers': bundle_id, 'ThrottleInterval': 1}
    write_plist(daemon, {**common, 'Label': DAEMON_LABEL,
                        'ProgramArguments': [str(service)], 'KeepAlive': True})
    write_plist(agent, {**common, 'Label': AGENT_LABEL,
                       'ProgramArguments': [str(executable), '--server'],
                       'LimitLoadToSessionType': ['Aqua', 'LoginWindow'],
                       'ProcessType': 'Interactive',
                       'KeepAlive': {'SuccessfulExit': False}})
    run('sudo', 'launchctl', 'bootstrap', 'system', daemon)
    run('launchctl', 'bootstrap', f'gui/{uid}', agent)
    run('open', '-a', APP)

    # CLI exit status alone is insufficient: RustDesk reports some password
    # errors with exit status zero. Require its explicit acknowledgement.
    password_set = False
    for _ in range(12):
        result = run('sudo', executable, '--password', secrets['MAC_TEST_PASSWORD'],
                     private=True, check=False, timeout=10)
        if result.returncode == 0 and result.stdout.strip() == 'Done!':
            password_set = True
            break
        time.sleep(3)
    if not password_set:
        raise RuntimeError('RustDesk did not confirm the permanent password; ending setup')
    remote_id = ''
    for _ in range(12):
        value = run('sudo', executable, '--get-id', check=False, timeout=10).stdout.strip()
        if re.fullmatch(r'[0-9]{6,16}', value) and int(value):
            remote_id = value
            break
        time.sleep(3)
    if not remote_id:
        raise RuntimeError('RustDesk did not register a usable remote ID')
    deadline = datetime.datetime.fromtimestamp(int(os.environ['MAC_TEST_DEADLINE']),
                                              datetime.timezone.utc).isoformat()
    summary = f'''## macOS test desktop

RustDesk ID: **{remote_id}**

Use the password you stored in `MAC_TEST_PASSWORD` on your Windows RustDesk client.
macOS user: `{console_user}`; administrator password: `MAC_TEST_ADMIN_PASSWORD`.
Session deadline: **{deadline}**; job has a 30-minute hard limit.

RustDesk is registered. Confirm screen capture and keyboard/mouse control after
connecting; registration alone does not prove GUI access.

Transfer the unpublished CI DMG from Windows. No build, release publication or
access to the private source repository is performed here.
Cancel the run or create `~/Desktop/END-MAC-TEST` to finish early.
'''
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as output:
        output.write(summary)
    print(f'RustDesk ID: {remote_id}\nSession deadline: {deadline}', flush=True)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 4 and sys.argv[1] == '--grant-permissions':
            if os.geteuid() != 0:
                raise RuntimeError('Permission helper requires administrator privileges')
            grant_permissions(sys.argv[2], sys.argv[3])
        else:
            main()
    except (RuntimeError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        # Never include command arguments: they may contain a password.
        if isinstance(error, subprocess.TimeoutExpired):
            message = 'A setup command timed out; ending the session'
        else:
            message = str(error)
        print('Setup failed: ' + message, file=sys.stderr)
        sys.exit(1)
