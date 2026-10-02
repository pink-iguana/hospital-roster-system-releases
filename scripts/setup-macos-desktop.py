#!/usr/bin/env python3
"""Set up a bounded installer QA session on a disposable GitHub macOS runner."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import socket
import subprocess
import sys
import time


VERSION = '1.4.9'
ARCHIVE_SHA256 = 'f7935597b247d42c8f2a2ed71176a9f5868018cd9e1a33b8096418a668c8caf0'
APP = Path('/Applications/RustDesk.app')
DAEMON_LABEL = 'com.carriez.RustDesk_service'
AGENT_LABEL = 'com.carriez.RustDesk_server'
ADMIN_USER = 'mac-test-admin'


def redact_secrets(message):
    values = [os.environ.get(name, '') for name in
              ('MAC_TEST_PASSWORD', 'MAC_TEST_ADMIN_PASSWORD')]
    for value in sorted(filter(None, values), key=len, reverse=True):
        message = message.replace(value, '[REDACTED]')
    return message


def run(*args, private=False, check=True, timeout=60):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True,
                            timeout=timeout)
    if check and result.returncode:
        detail = redact_secrets(result.stderr.strip())
        # Secret-bearing commands may report useful errors on stdout instead.
        if private and not detail:
            detail = redact_secrets(result.stdout.strip())
        suffix = ': ' + detail if detail else ''
        raise RuntimeError(f'{Path(str(args[0])).name} failed '
                           f'(exit {result.returncode}){suffix}')
    return result


def create_test_admin(password):
    # Leave the active runner account intact: resetting its password can require
    # its existing password/Secure Token credentials, even when running as root.
    run('sudo', '-n', 'true')
    if run('id', '-u', ADMIN_USER, check=False).returncode == 0:
        raise RuntimeError(f'Temporary administrator {ADMIN_USER} already exists')
    print(f'Creating temporary administrator {ADMIN_USER}', flush=True)
    run('sudo', '-n', 'sysadminctl', '-addUser', ADMIN_USER,
        '-fullName', 'macOS Installer Test Administrator',
        '-password', password, '-admin', private=True)
    # sysadminctl can exit successfully without creating a usable account.
    run('dscl', '.', '-authonly', ADMIN_USER, password, private=True)
    groups = run('id', '-Gn', ADMIN_USER).stdout.split()
    if 'admin' not in groups:
        raise RuntimeError('Temporary test account is not an administrator')


def read_desktop_status(address=None):
    # RustDesk 1.4.9's main IPC uses tagged JSON with BytesCodec framing.
    # Query the desktop user's actual --server process, rather than accepting
    # --get-id's fallback to a stored ID in a separate root configuration.
    address = address or f'/tmp/RustDesk-{os.getuid()}/ipc'
    deadline = time.monotonic() + 5
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(address)

        def receive_exact(size):
            result = bytearray()
            while len(result) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('RustDesk desktop status query timed out')
                connection.settimeout(remaining)
                chunk = connection.recv(size - len(result))
                if not chunk:
                    raise RuntimeError('RustDesk desktop status connection closed')
                result.extend(chunk)
            return bytes(result)

        def query(kind, content):
            payload = json.dumps({'t': kind, 'c': content}, separators=(',', ':')).encode()
            # These two read-only queries fit in a one-byte frame header.
            connection.sendall(bytes([len(payload) << 2]) + payload)
            while True:
                first = receive_exact(1)
                width = (first[0] & 3) + 1
                header = first + receive_exact(width - 1)
                size = int.from_bytes(header, 'little') >> 2
                if not 0 < size <= 65536:
                    raise RuntimeError('Invalid RustDesk desktop status frame')
                try:
                    response = json.loads(receive_exact(size))
                except (ValueError, UnicodeError) as error:
                    raise RuntimeError('Invalid RustDesk desktop status response') from error
                if isinstance(response, dict) and response.get('t') == kind:
                    return response.get('c')

        config = query('Config', ['id', None])
        state = query('OnlineStatus', None)
    if (not isinstance(config, list) or len(config) != 2 or config[0] != 'id'
            or not isinstance(config[1], str)
            or not re.fullmatch(r'[0-9]{6,16}', config[1]) or not int(config[1])):
        raise RuntimeError('RustDesk desktop service has no usable ID')
    if (not isinstance(state, list) or len(state) != 2
            or type(state[0]) is not int or type(state[1]) is not bool):
        raise RuntimeError('Invalid RustDesk desktop online status')
    return config[1], state[0], state[1]


def wait_for_desktop_online():
    last_status = 'Desktop service has not responded'
    for attempt in range(30):
        try:
            remote_id, latency, confirmed = read_desktop_status()
            last_status = (f'ID={remote_id}, server_latency={latency}, '
                           f'key_confirmed={confirmed}')
            if latency > 0 and confirmed:
                print('RustDesk desktop service is online: ' + last_status, flush=True)
                return remote_id
        except (OSError, RuntimeError) as error:
            last_status = redact_secrets(str(error))
        if attempt % 5 == 0:
            print('Waiting for RustDesk network: ' + last_status, flush=True)
        if attempt < 29:
            time.sleep(2)
    raise RuntimeError('RustDesk desktop did not become online; ' + last_status)


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
    create_test_admin(secrets['MAC_TEST_ADMIN_PASSWORD'])

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
    # -r- writes requirements to stdout; codesign's status messages use stderr.
    requirement = run('codesign', '-d', '-r-', APP).stdout
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
    remote_id = wait_for_desktop_online()
    deadline = datetime.datetime.fromtimestamp(int(os.environ['MAC_TEST_DEADLINE']),
                                              datetime.timezone.utc).isoformat()
    summary = f'''## macOS test desktop

RustDesk ID: **{remote_id}**

Use the password you stored in `MAC_TEST_PASSWORD` on your Windows RustDesk client.
Desktop user: `{console_user}`.
For system authentication prompts, use administrator `{ADMIN_USER}` with
the password stored in `MAC_TEST_ADMIN_PASSWORD`.
Session deadline: **{deadline}**; job has a 125-minute hard limit for cleanup.

RustDesk's desktop service confirmed an online connection during setup.
Confirm screen capture and keyboard/mouse control after connecting; the setup
check does not prove Windows-to-Mac reachability or GUI access.

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
        print('Setup failed: ' + redact_secrets(message), file=sys.stderr)
        sys.exit(1)
