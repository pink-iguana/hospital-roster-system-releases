"""Verify public Qt distribution and native replacement; never publish assets."""
import argparse
from contextlib import contextmanager
import difflib
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import shutil
import subprocess
import tarfile
import time
import traceback
import urllib.request
import zipfile

REPOSITORY = 'pink-iguana/hospital-roster-system-releases'
APP_PATTERN = r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?'
SOURCE_PATTERN = r'qt-\d+\.\d+\.\d+-source(?:-\d+)?'
STAGES = ('desktop', 'installation_and_baseline', 'corresponding_source',
          'notices_and_rights', 'modified_qt_build', 'replacement', 'modified_gui')


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'HRS-Qt-compliance'})
    return urllib.request.urlopen(request, timeout=120)


def fetch_json(url):
    with fetch(url) as stream:
        return json.load(stream)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise RuntimeError(f'Unsafe archive path: {name}')
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f'Archive path escapes root: {name}')
    return path


def newest(releases, pattern, tag=''):
    candidates = [release for release in releases if not release['draft'] and
                  re.fullmatch(pattern, release['tag_name']) and
                  (not tag or release['tag_name'] == tag)]
    if not candidates:
        raise RuntimeError(f'No published release matches {tag or pattern}')
    return max(candidates, key=lambda release: (release['published_at'], release['id']))


def resolve(output):
    releases = []
    for page in range(1, 101):
        batch = fetch_json(f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100&page={page}')
        releases.extend(batch)
        if len(batch) < 100:
            break
    app = newest(releases, APP_PATTERN, os.environ.get('APP_TAG', ''))
    source = newest(releases, SOURCE_PATTERN, os.environ.get('QT_SOURCE_TAG', ''))
    for release in (app, source):
        for asset in release['assets']:
            if asset['state'] != 'uploaded' or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''):
                raise RuntimeError(f'Asset lacks a verified digest: {asset["name"]}')
    platform = os.environ.get('VERIFY_PLATFORM', 'both')
    runners = {'windows': 'windows-2022', 'macos': 'macos-15'}
    selected = list(runners) if platform == 'both' else [platform]
    matrix = {'include': [{'platform': item, 'runner': runners[item]} for item in selected]}
    output.write_text(json.dumps({'repository': REPOSITORY, 'app': app, 'source': source}, indent=2))
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write('matrix=' + json.dumps(matrix) + '\n')
    print(f'Selected {app["tag_name"]} and {source["tag_name"]}')


def asset(release, name):
    matches = [item for item in release['assets'] if item['name'] == name]
    if len(matches) != 1:
        raise RuntimeError(f'Expected exactly one public asset: {name}')
    return matches[0]


def check_source_reference(notice, url, sha):
    if 'Download URL: ' + url not in notice or 'SHA-256: ' + sha not in notice:
        raise RuntimeError('Selected Qt source does not match the installed application')


def download(release, name, directory):
    entry = asset(release, name)
    destination = safe_path(directory, name)
    directory.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or digest(destination) != entry['digest'][7:]:
        temporary = destination.with_suffix(destination.suffix + '.part')
        for attempt in range(3):
            try:
                with fetch(entry['browser_download_url']) as stream, temporary.open('wb') as target:
                    shutil.copyfileobj(stream, target)
                if digest(temporary) != entry['digest'][7:]:
                    raise RuntimeError(f'Public asset checksum mismatch: {name}')
                temporary.replace(destination)
                break
            except OSError:
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(2)
    if destination.stat().st_size != entry['size']:
        raise RuntimeError(f'Public asset size mismatch: {name}')
    return destination


class Verification:
    def __init__(self, platform, selection, work):
        self.platform = platform
        self.data = json.loads(selection.read_text())
        self.work = work.resolve()
        self.evidence = self.work / 'evidence'
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.native = importlib.import_module('qt_compliance_' + platform)
        self.report = {'platform': platform, 'appTag': self.data['app']['tag_name'],
                       'sourceTag': self.data['source']['tag_name'],
                       'status': 'incomplete', 'stages': {name: {'status': 'not_run'} for name in STAGES}}
        (self.evidence / 'selection.json').write_text(json.dumps(self.data, indent=2))
        self.current = 'desktop'
        self.command_number = 0
        self.installer = None
        self.installed = False

    def save(self):
        (self.evidence / 'results.json').write_text(json.dumps(self.report, indent=2) + '\n')
        rows = [f'# Qt compliance verification: {self.platform}', '',
                f'Application: **{self.report["appTag"]}**; source: **{self.report["sourceTag"]}**', '',
                f'Result: **{self.report["status"]}**', '', '| Check | Result |', '| --- | --- |']
        rows += [f'| {name} | {item["status"]} |' for name, item in self.report['stages'].items()]
        if 'error' in self.report:
            rows += ['', 'Failure: ' + self.report['error']]
        rows += ['', 'Technical evidence for the tested distribution. Consumer Gatekeeper behaviour,',
                 'general roster correctness and comprehensive legal assessment are outside this check.']
        (self.evidence / 'summary.md').write_text('\n'.join(rows) + '\n')

    @contextmanager
    def stage(self, name):
        self.current = name
        started = time.monotonic()
        self.report['stages'][name]['status'] = 'running'
        self.save()
        try:
            yield
        except Exception:
            self.report['stages'][name]['status'] = 'failed'
            raise
        else:
            self.report['stages'][name]['status'] = 'passed'
        finally:
            self.report['stages'][name]['seconds'] = round(time.monotonic() - started, 2)
            self.save()

    def run(self, command, cwd=None, env=None, timeout=120, accepted=(0,)):
        self.command_number += 1
        log = self.evidence / f'{self.command_number:03d}-{self.current}.log'
        print('Running:', ' '.join(map(str, command)), flush=True)
        with log.open('w', encoding='utf-8') as stream:
            stream.write(json.dumps(list(map(str, command))) + '\n')
            stream.flush()
            process = subprocess.Popen(list(map(str, command)), cwd=cwd,
                                       env=env if env is not None else getattr(self, 'build_env', None),
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != 'nt')
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError(f'Timed out: {command[0]} (see {log.name})')
        if code not in accepted:
            raise RuntimeError(f'Command failed ({code}): {command[0]} (see {log.name})')
        return '\n'.join(log.read_text(encoding='utf-8', errors='replace').splitlines()[1:])

    def baseline(self):
        release = self.data['app']
        version = re.fullmatch(r'v(\d+\.\d+\.\d+)(?:-.*)?', release['tag_name'])[1]
        suffix = 'windows-x64.msi' if self.platform == 'windows' else 'macos-arm64.dmg'
        downloads = self.work / 'downloads'
        self.installer = download(release, f'HospitalRosterSystem-{version}-{suffix}', downloads)
        self.guide = download(release, 'HospitalRosterSystem-User-Guide.pdf', downloads)
        self.binary_licence = download(release, 'HospitalRosterSystem-BINARY-USE-LICENCE.txt', downloads)
        ledger = download(release, 'SHA256SUMS.txt', downloads)
        entries = dict((name, sha) for sha, name in (row.split('  ', 1) for row in ledger.read_text().splitlines()))
        for path in (self.installer, self.guide, self.binary_licence):
            if entries.get(path.name) != digest(path):
                raise RuntimeError(f'Release checksum ledger differs: {path.name}')
        self.app = self.native.install(self.installer, self.work, self.run)
        self.installed = True
        self.exercise(self.app, 'baseline')

    def exercise(self, app, label):
        environment = dict(os.environ)
        for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_QPA_PLATFORM',
                    'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH'):
            environment.pop(key, None)
        with (self.evidence / f'{label}-app.log').open('w') as stream:
            process = subprocess.Popen([str(self.native.executable(app))], cwd=self.work,
                                       env=environment, stdout=stream, stderr=subprocess.STDOUT)
            try:
                paths = self.native.gui(process, self.evidence, label)
                if process.poll() is not None:
                    raise RuntimeError('Application exited during GUI interaction')
                required = ('Qt6Core', 'Qt6Gui', 'Qt6Widgets',
                            'qwindows' if self.platform == 'windows' else 'qcocoa')
                for name in required:
                    if not any(name.lower() in Path(path).name.lower() for path in paths):
                        raise RuntimeError(f'Loaded module evidence is missing {name}')
                modules = []
                for value in paths:
                    path = Path(value).resolve()
                    if not path.is_relative_to(app.resolve()):
                        raise RuntimeError(f'Qt loaded outside the tested app: {path}')
                    if label == 'modified' and self.replacement_hashes.get(str(path)) != digest(path):
                        raise RuntimeError(f'Loaded Qt differs from staged replacement: {path}')
                    modules.append({'path': str(path), 'sha256': digest(path)})
                (self.evidence / f'{label}-loaded-qt.json').write_text(json.dumps(modules, indent=2))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def source(self):
        release = self.data['source']
        manifest_path = download(release, 'Qt_SOURCE_MANIFEST.json', self.work / 'downloads')
        self.manifest = json.loads(manifest_path.read_text())
        archive_path = download(release, self.manifest['asset'], self.work / 'downloads')
        if self.manifest['sha256'] != digest(archive_path):
            raise RuntimeError('Qt source manifest differs from source archive')
        notice = (self.native.licences(self.app) / 'Qt_SOURCE_AVAILABILITY.txt').read_text()
        self.source_url = asset(release, self.manifest['asset'])['browser_download_url']
        check_source_reference(notice, self.source_url, digest(archive_path))
        root = self.work / 'source'
        root.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                safe_path(root, member.filename)
            archive.extractall(root)
        for row in (root / 'CONTENTS.sha256').read_text().splitlines():
            sha, name = row.split('  ', 1)
            if digest(safe_path(root, name)) != sha:
                raise RuntimeError(f'Internal source checksum differs: {name}')
        self.catalog = json.loads((root / 'Qt_COMPONENTS.json').read_text())
        if self.manifest['components'] != self.catalog['components']:
            raise RuntimeError('Source manifest and archive inventories differ')
        for entry in self.catalog['components']:
            if digest(safe_path(root, entry['source']['path'])) != entry['source']['sha256']:
                raise RuntimeError(f'Component source checksum differs: {entry["ref"]}')
            if digest(safe_path(root, entry['recipe'])) != entry['recipe_sha256']:
                raise RuntimeError(f'Component recipe checksum differs: {entry["ref"]}')
        self.source_root = root
        self.host = 'windows-x64' if self.platform == 'windows' else 'macos-arm64'
        for name in ('default', 'qt-graph.json', 'conan-profile.txt', 'toolchain.txt'):
            if not (root / self.host / name).is_file():
                raise RuntimeError(f'Missing native source input: {name}')
        self.report['sourceSHA256'] = digest(archive_path)
        self.report['sourceURL'] = self.source_url
        # The archive's inner sources remain; remove only the redundant outer ZIP.
        archive_path.unlink()

    def notices(self):
        from pypdf import PdfReader
        licences = self.native.licences(self.app)
        records = json.loads((licences / 'DEPENDENCY_MANIFEST.json').read_text())
        refs = {item['ref'] for item in records}
        required = {item['ref'] for item in self.catalog['platforms'][self.host]}
        if not required <= refs:
            raise RuntimeError('Installed Qt dependency notice coverage is incomplete')
        for record in records:
            directory = safe_path(licences, record['directory'])
            if not directory.is_dir() or not any(path.is_file() for path in directory.rglob('*')):
                raise RuntimeError(f'Empty dependency notice directory: {record["ref"]}')
        for entry in self.catalog['components']:
            if entry['ref'] not in required:
                continue
            component = entry['ref'].split('#')[0].replace('/', '-')
            for name, sha in entry['notices'].items():
                path = safe_path(licences / component / 'audited-source-notices', name)
                if digest(path) != sha:
                    raise RuntimeError(f'Installed audited notice differs: {component}/{name}')
        qt_ref = next(ref for ref in required if ref.startswith('qt/'))
        qt_dir = licences / qt_ref.split('#')[0].replace('/', '-')
        for name in ('LGPL-3.0-only.txt', 'GPL-3.0-only.txt'):
            installed = qt_dir / 'LICENSES' / name
            source = self.source_root / 'Notices' / qt_dir.name / 'LICENSES' / name
            if digest(installed) != digest(source):
                raise RuntimeError(f'Qt licence text differs: {name}')
        for name in ('THIRD_PARTY_NOTICES.txt', 'Qt_BUILD_INSTRUCTIONS.txt', 'Qt_NOTICE_AUDIT.md'):
            if not (licences / name).is_file():
                raise RuntimeError(f'Missing installed document: {name}')
        installed_licence = licences / 'HospitalRosterSystem-BINARY-USE-LICENCE.txt'
        normal = lambda path: ' '.join(path.read_text(encoding='utf-8-sig').split())
        if normal(installed_licence) != normal(self.binary_licence):
            raise RuntimeError('Installed binary licence differs from public release')
        text = normal(installed_licence).lower()
        for fragment in ('third-party', 'modify or replace', 'reverse engineer',
                         'debugging modifications', 'does not terminate or restrict rights'):
            if fragment not in text:
                raise RuntimeError(f'Recipient-rights clause requires review: {fragment}')
        doc_root = self.app / ('Documentation' if self.platform == 'windows' else 'Contents/Resources/Documentation')
        guide = doc_root / self.guide.name
        if digest(guide) != digest(self.guide):
            raise RuntimeError('Installed guide differs from public release')
        text = ' '.join(page.extract_text() or '' for page in PdfReader(guide).pages[:2]).lower()
        if 'qt' not in text or 'lgpl' not in text:
            raise RuntimeError('Prominent Qt/LGPL notice missing from guide opening pages')
        (self.evidence / 'dependency-manifest.json').write_text(json.dumps(records, indent=2))

    def build(self):
        qt = next(item for item in self.catalog['components'] if item['ref'].startswith('qt/'))
        name = 'qtbase/src/corelib/global/qlibraryinfo.cpp'
        original = None
        with tarfile.open(self.source_root / qt['source']['path'], 'r|*') as archive:
            for member in archive:
                if member.isfile() and member.name.endswith('/' + name):
                    original = archive.extractfile(member).read().decode()
                    break
        if original is None or original.count('return QT_VERSION_STR;') != 1:
            raise RuntimeError('Qt version-marker patch needs review for this source version')
        changed = original.replace('return QT_VERSION_STR;', 'return QT_VERSION_STR "-lgpl-check";')
        patch = ''.join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                            fromfile='a/' + name, tofile='b/' + name))
        patch_path = self.evidence / 'user-qt.patch'
        patch_path.write_text(patch, encoding='utf-8', newline='\n')
        (self.evidence / 'patch-provenance.json').write_text(json.dumps({
            'dateUTC': time.strftime('%Y-%m-%d', time.gmtime()), 'originalRecipe': qt['ref'],
            'patchSHA256': digest(patch_path), 'change': 'qVersion() reports -lgpl-check'}, indent=2))
        self.home = self.work / 'modified-conan'
        environment = dict(os.environ, CONAN_HOME=str(self.home))
        helper = self.source_root / 'rebuild_qt.py'
        self.run(['python', str(helper), '--platform', self.host, '--home', str(self.home),
                  '--qt-patch', str(patch_path), '--prepare-only'], env=environment, timeout=300)
        command = json.loads((self.home / 'rebuild-command.json').read_text())
        if self.platform == 'macos':
            inputs = self.app / 'Contents/Resources/QtBuildInputs'
            for profile in ('default', 'macos-arm64'):
                shutil.copy2(inputs / profile, self.home / 'profiles' / profile)
            # Preserve the application's dependency locks while substituting only modified Qt.
            lock = json.loads((inputs / 'conan-macos-arm64-release.lock').read_text())
            modified = json.loads((self.home / 'modified-qt-export.json').read_text())['reference']
            lock['requires'] = [modified if item.split('%')[0] == qt['ref'] else item for item in lock['requires']]
            (self.home / 'modified-qt.lock').write_text(json.dumps(lock, indent=2))
            record = (inputs / 'toolchain.txt').read_text()
            match = re.search(r'(/Applications/Xcode[^\s]*/Contents/Developer)', record)
            if not match or not Path(match[1]).is_dir():
                raise RuntimeError('The app-recorded Xcode is unavailable on this runner')
            environment['DEVELOPER_DIR'] = match[1]
            shutil.copytree(inputs, self.evidence / 'native-build-inputs')
        else:
            result = self.run(['conan', 'profile', 'show', '-pr', 'default'], env=environment)
            if 'compiler.version=194' not in result:
                raise RuntimeError('Expected MSVC 194 for this Windows source configuration')
            shutil.copytree(self.source_root / self.host, self.evidence / 'native-build-inputs')
        self.build_env = environment
        (self.evidence / 'rebuild-command.json').write_text(json.dumps(command, indent=2))
        self.run(command, env=environment, timeout=300 * 60)
        graph_path = self.home / 'rebuild-graph.json'
        shutil.copy2(graph_path, self.evidence / graph_path.name)
        shutil.copy2(self.home / 'modified-qt-export.json', self.evidence / 'modified-qt-export.json')
        graph = json.loads(graph_path.read_text())
        nodes = [node for node in graph['graph']['nodes'].values()
                 if node.get('name') == 'qt' and node.get('context') == 'host']
        if len(nodes) != 1 or not nodes[0].get('package_folder') or str(nodes[0]['options']['shared']).lower() != 'true':
            raise RuntimeError('Modified Qt build lacks the expected shared package')
        if nodes[0]['ref'] == qt['ref']:
            raise RuntimeError('Qt build did not use the modified recipe')
        self.package = Path(nodes[0]['package_folder'])

    def replacement(self):
        target = self.work / 'replacement' / self.app.name
        target.parent.mkdir(exist_ok=True)
        shutil.copytree(self.app, target, symlinks=True)
        before = digest(self.native.executable(target))
        validator = target / ('Validator' if self.platform == 'windows' else 'Contents/Frameworks/Validator')
        original_validator = {str(path.relative_to(validator)): digest(path)
                              for path in validator.rglob('*') if path.is_file()}
        code = self.native.text_code(self.native.executable(target), self.run) if self.platform == 'macos' else None
        self.native.replace(target, self.package, self.run)
        if self.platform == 'windows' and digest(self.native.executable(target)) != before:
            raise RuntimeError('Application executable changed during replacement')
        if self.platform == 'macos' and self.native.text_code(self.native.executable(target), self.run) != code:
            raise RuntimeError('Application executable instructions changed during signing')
        if original_validator != {str(path.relative_to(validator)): digest(path)
                                  for path in validator.rglob('*') if path.is_file()}:
            raise RuntimeError('Private Validator payload changed during Qt replacement')
        version = self.native.probe(target, self.package, self.work, self.run)
        if version != self.manifest['version'] + '-lgpl-check':
            raise RuntimeError(f'Modified Qt version marker was not observed: {version}')
        self.report['modifiedQtVersion'] = version
        self.replacement_hashes = {str(path.resolve()): digest(path) for path in target.rglob('*')
                                   if path.is_file() and (path.suffix.lower() in ('.dll', '.dylib'))}
        (self.evidence / 'replacement-hashes.json').write_text(json.dumps(self.replacement_hashes, indent=2))
        self.modified = target

    def verify(self):
        try:
            actions = (lambda: self.native.preflight(self.work), self.baseline, self.source,
                       self.notices, self.build, self.replacement,
                       lambda: self.exercise(self.modified, 'modified'))
            for name, action in zip(STAGES, actions):
                with self.stage(name):
                    action()
            self.report['status'] = 'passed'
        except Exception as error:
            self.report['status'] = 'failed'
            self.report['error'] = str(error)
            (self.evidence / 'failure.txt').write_text(traceback.format_exc())
            raise
        finally:
            if self.installed:
                try:
                    self.native.cleanup(self.installer, self.run)
                except Exception as error:
                    self.report['cleanupError'] = str(error)
                    self.report['status'] = 'failed'
            self.save()
        if self.report['status'] != 'passed':
            raise RuntimeError('Verification cleanup failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    select = sub.add_parser('resolve')
    select.add_argument('--output', type=Path, required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--platform', choices=('windows', 'macos'), required=True)
    verify.add_argument('--selection', type=Path, required=True)
    verify.add_argument('--work', type=Path, required=True)
    report = sub.add_parser('report-setup-failure')
    report.add_argument('--platform', choices=('windows', 'macos'), required=True)
    report.add_argument('--selection', type=Path, required=True)
    report.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'resolve':
        resolve(args.output)
    elif args.command == 'verify':
        Verification(args.platform, args.selection, args.work).verify()
    else:
        verification = Verification(args.platform, args.selection, args.work)
        verification.report['status'] = 'failed'
        verification.report['stages']['desktop']['status'] = 'failed'
        verification.report['error'] = 'Native tool/GUI setup failed before verification; inspect Actions setup logs'
        verification.save()
