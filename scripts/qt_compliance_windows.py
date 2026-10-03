"""Windows native installation, GUI and loaded-module checks."""
import ctypes
import json
import subprocess
import time
from pathlib import Path


def preflight(work):
    from pywinauto import Desktop
    station = ctypes.windll.user32.GetProcessWindowStation
    station.restype = ctypes.c_void_p
    flags, needed = (ctypes.c_uint32 * 3)(), ctypes.c_uint32()
    query = ctypes.windll.user32.GetUserObjectInformationW
    query.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                      ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    if not query(station(), 1, flags, ctypes.sizeof(flags), ctypes.byref(needed)) or not flags[2] & 1:
        raise RuntimeError('Windows runner has no visible interactive window station')
    Desktop(backend='uia').windows()


def install(installer, work, run):
    log = work / 'evidence/msi-install.log'
    run(['msiexec.exe', '/i', str(installer), '/qn', '/norestart', '/l*v', str(log)],
        timeout=300, accepted=(0, 3010))
    app = Path('C:/Program Files/HospitalRosterSystem')
    if not (app / 'HospitalRosterSystem.exe').is_file():
        raise RuntimeError('MSI did not install the expected application')
    return app


def executable(app):
    return app / 'HospitalRosterSystem.exe'


def licences(app):
    return app / 'Licences'


def gui(process, evidence, label):
    from pywinauto import Application
    client = Application(backend='uia').connect(process=process.pid, timeout=60)
    window = client.window(title_re=r'Hospital Roster System.*')
    window.wait('visible enabled ready', timeout=60)
    records = []
    for title in ('Roster', 'Preferences'):
        tab = window.child_window(title=title, control_type='TabItem')
        tab.wait('visible enabled', timeout=30)
        tab.select()
        if not tab.is_selected():
            raise RuntimeError(f'GUI did not select {title}')
        records.append({'tab': title, 'selected': True})
    (evidence / f'{label}-gui.json').write_text(json.dumps(records, indent=2))
    command = (f'(Get-Process -Id {process.pid}).Modules | '
               'Select-Object ModuleName,FileName | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            text=True, capture_output=True, check=True, timeout=30)
    modules = json.loads(result.stdout)
    return [item['FileName'] for item in modules
            if item['ModuleName'].lower().startswith('qt6') or
            item['ModuleName'].lower() == 'qwindows.dll']


def replace(app, package, run):
    import shutil
    for old in app.glob('Qt6*.dll'):
        source = package / 'bin' / old.name
        if not source.is_file():
            raise RuntimeError(f'Rebuilt Qt lacks {old.name}')
        shutil.copy2(source, old)
    for directory in (package / 'plugins').iterdir():
        target = app / directory.name
        if directory.is_dir() and target.is_dir():
            for old in target.glob('*.dll'):
                source = directory / old.name
                if not source.is_file():
                    raise RuntimeError(f'Rebuilt Qt lacks plugin {old.name}')
                shutil.copy2(source, old)


def probe(app, package, work, run):
    source = work / 'version-probe.cpp'
    source.write_text('#include <QtCore/QtGlobal>\n#include <cstdio>\n'
                      'int main(){std::puts(qVersion());}\n')
    output = app / 'qt-compliance-version-probe.exe'
    run(['cl.exe', '/nologo', '/EHsc', '/std:c++17', '/Zc:__cplusplus', '/DQT_CORE_LIB',
         '/I' + str(package / 'include'), str(source),
         str(package / 'lib/Qt6Core.lib'), '/Fe:' + str(output)], cwd=work)
    try:
        return run([str(output)]).strip()
    finally:
        output.unlink(missing_ok=True)


def cleanup(installer, run):
    run(['msiexec.exe', '/x', str(installer), '/qn', '/norestart'],
        timeout=300, accepted=(0, 3010))
