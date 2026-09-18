#!/usr/bin/env python3
"""Build a real bundled-engine Release artifact and collect ad-hoc engineering evidence.

No certificate/password is read or exported. Ad-hoc signing exercises the Sandbox
and Hardened Runtime only; this is never labelled a notarized distribution build.
The release binary is not replaced by a test double. A separate disposable copy
hosts a probe built from the same production Swift process/transport sources.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from bundle_engine import BundleError, ROOT, run, sha256, source_inventory, stage_engine, validate_links

MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
          b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


def macho_files(root: Path) -> list[Path]:
    values = []
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as source:
                if source.read(4) in MAGICS:
                    values.append(path)
    return values


def validate_load_paths(text: str, *, identification: str = '') -> None:
    """Check loaded dependencies, not the dylib's own LC_ID_DYLIB metadata."""
    identities = [line.strip() for line in identification.splitlines()[1:] if line.strip()]
    if len(identities) > 1:
        raise BundleError('Ambiguous Mach-O install identity')
    lines = text.splitlines()[1:]
    if identities:
        if not lines or lines[0].strip().split(' (', 1)[0] != identities[0]:
            raise BundleError('Mach-O identification and load list disagree')
        lines = lines[1:]
    for line in lines:
        dependency = line.strip().split(' (', 1)[0]
        if not dependency:
            continue
        if not dependency.startswith(('@loader_path/', '@executable_path/', '@rpath/',
                                      '/usr/lib/', '/System/Library/')):
            raise BundleError('Mach-O has a non-relocatable library dependency')


def sign_bundle(app: Path, logs: Path) -> None:
    validate_links(app)
    interpreter = (app/'Contents/Resources/LocalEngine/bin/python3').resolve(strict=True)
    binaries = macho_files(app)
    for index, binary in enumerate(binaries):
        loads = run(['otool', '-arch', 'arm64', '-L', str(binary)], cwd=ROOT, log=logs/f'loads-{index}.log')
        identity = run(['otool', '-arch', 'arm64', '-D', str(binary)],
                       cwd=ROOT, log=logs/f'identity-{index}.log')
        validate_load_paths(loads, identification=identity)
        # Wheels may be universal2, but every native dependency must contain arm64.
        archs = run(['lipo', '-archs', str(binary)], cwd=ROOT, log=logs/f'arch-{index}.log')
        if 'arm64' not in archs.split():
            raise BundleError('Native dependency lacks arm64')
        options = ['--entitlements', str(ROOT/'macos-app/Packaging/Engine.entitlements')] if binary.resolve(strict=True) == interpreter else []
        run(['codesign', '--force', '--sign', '-', '--options', 'runtime', *options, str(binary)],
            cwd=ROOT, log=logs/f'sign-{index}.log')
    run(['codesign', '--force', '--sign', '-', '--options', 'runtime', '--entitlements',
         str(ROOT/'macos-app/Packaging/App.entitlements'), str(app)], cwd=ROOT, log=logs/'sign-app.log')
    for index, binary in enumerate(binaries):
        run(['codesign','--verify','--strict','--verbose=2',str(binary)],cwd=ROOT,log=logs/f'verify-{index}.log')
    run(['codesign','--verify','--deep','--strict','--verbose=2',str(app)],cwd=ROOT,log=logs/'verify-app.log')
    for label, target, expected in [('app', app, 'App.entitlements'), ('engine', interpreter, 'Engine.entitlements')]:
        raw = run(['codesign', '-d', '--entitlements', ':-', str(target)],
                  cwd=ROOT, log=logs/f'{label}-entitlements.log')
        match = re.search(r'<\?xml.*?</plist>', raw, re.S)
        if not match or plistlib.loads(match.group().encode()) != plistlib.loads((ROOT/'macos-app/Packaging'/expected).read_bytes()):
            raise BundleError('Signed entitlements differ from the reviewed Sandbox boundary')
        details = run(['codesign','-dvv',str(target)],cwd=ROOT,log=logs/f'{label}-signature.log')
        if 'runtime' not in details:
            raise BundleError('Hardened Runtime flag missing')


def minimal_environment() -> dict[str, str]:
    # Preserve only launch/session basics. Deliberately hostile Python variables
    # prove that -E and absolute bundled paths do not consume the developer venv.
    keep = {k: v for k, v in os.environ.items() if k in {'HOME','TMPDIR','USER','LOGNAME','__CF_USER_TEXT_ENCODING'}}
    keep.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin', LANG='en_US.UTF-8',
                PYTHONHOME='/nonexistent-wom-host-python', PYTHONPATH='/nonexistent-wom-host-module',
                VIRTUAL_ENV='/nonexistent-wom-host-venv')
    return keep


def children(pid: int) -> list[tuple[int, str]]:
    raw = subprocess.check_output(['/bin/ps','-axo','pid=,ppid=,command='],text=True)
    result = []
    for line in raw.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[1] == str(pid):
            result.append((int(parts[0]), parts[2]))
    return result


def await_engine(app: subprocess.Popen, bundle: Path, *, previous: int | None = None) -> int:
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if app.poll() is not None:
            raise BundleError('Release App exited before Engine startup')
        candidates = [(pid, command) for pid, command in children(app.pid)
                      if str(bundle/'Contents/Resources/LocalEngine/bin/') in command and pid != previous]
        if len(candidates) == 1:
            return candidates[0][0]
        if len(candidates) > 1:
            raise BundleError('Release App launched duplicate engines')
        time.sleep(0.1)
    raise BundleError('Release App did not start its bundled Engine')


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def release_app_probe(bundle: Path, logs: Path) -> dict:
    executable = bundle/'Contents/MacOS/WorldOfMysteries'
    started = time.monotonic()
    known_children: list[int] = []
    with (logs/'release-app.log').open('wb') as log:
        app = subprocess.Popen([str(executable)], env=minimal_environment(), stdout=log, stderr=log)
        try:
            first = await_engine(app, bundle)
            known_children.append(first)
            spawned_ms = (time.monotonic() - started) * 1000
            # Wait for the App to finish its normal handshake and attach recovery.
            time.sleep(2)
            if not process_exists(first):
                raise BundleError('Bundled Engine exited after spawn')
            os.kill(first, signal.SIGKILL)
            second = await_engine(app, bundle, previous=first)
            known_children.append(second)
            time.sleep(2)
            if not process_exists(second):
                raise BundleError('Recovered bundled Engine exited')
            app.kill()
            app.wait(timeout=5)
            deadline = time.monotonic() + 6
            while process_exists(second) and time.monotonic() < deadline:
                time.sleep(0.1)
            if process_exists(second):
                raise BundleError('Engine outlived the force-quit Release App')
            return {'release_app_started': True, 'engine_spawn_ms': spawned_ms,
                    'engine_crash_recovered': True, 'app_force_quit_cleaned_engine': True,
                    'ui_interactive_acceptance': 'not-tested'}
        finally:
            if app.poll() is None:
                app.kill(); app.wait(timeout=5)
            for pid in known_children:
                # Only children spawned by this probe are eligible for cleanup.
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def packaged_probe(bundle: Path, work: Path, logs: Path) -> dict:
    probe = work/'Probe.app'
    shutil.copytree(bundle, probe, symlinks=True)
    swift = ROOT/'macos-app/WorldOfMysteries'
    names = ['IPCEnvelope','IPCFrameCodec','EngineRuntimeModels','EngineSocketTransport',
             'EngineIPCClient','EngineProcessManager']
    executable = probe/'Contents/MacOS/WorldOfMysteries'
    executable.unlink()
    run(['swiftc','-swift-version','6','-strict-concurrency=complete',
         *[str(swift/f'{name}.swift') for name in names],
         str(ROOT/'scripts/packaging/EnginePackageProbe.swift'), '-o',str(executable)],
        cwd=ROOT,log=logs/'probe-compile.log',timeout=180)
    # A different identity gives the engineering host its own Sandbox container.
    plist = probe/'Contents/Info.plist'
    data = plistlib.loads(plist.read_bytes())
    data['CFBundleIdentifier'] = 'dev.worldofmysteries.packaging-probe'
    plist.write_bytes(plistlib.dumps(data))
    run(['codesign','--force','--sign','-','--options','runtime','--entitlements',
         str(ROOT/'macos-app/Packaging/App.entitlements'),str(probe)],cwd=ROOT,log=logs/'probe-sign.log')
    raw = run([str(executable)],cwd=work,log=logs/'probe-runtime.log',env=minimal_environment(),timeout=60)
    result = json.loads(raw.strip().splitlines()[-1])
    if result.get('passed') is not True:
        raise BundleError('Packaged production transport probe failed')
    return result


def build(output: Path) -> None:
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise BundleError('Release packaging requires macOS arm64')
    if output.exists() or output.is_symlink():
        raise BundleError('Output exists: use a new isolated workspace, never overwrite a package')
    output.mkdir(parents=True)
    logs = output/'logs'
    logs.mkdir()
    with tempfile.TemporaryDirectory(prefix='wom-package-') as temporary:
        work = Path(temporary).resolve()
        run(['xcodebuild','-project','macos-app/WorldOfMysteries.xcodeproj','-scheme','WorldOfMysteries',
             '-configuration','Release','-destination','platform=macOS,arch=arm64',
             '-derivedDataPath',str(work/'derived'),'CODE_SIGNING_ALLOWED=NO','build'],
            cwd=ROOT,log=logs/'release-build.log',timeout=1200)
        original = work/'derived/Build/Products/Release/WorldOfMysteries.app'
        if not original.is_dir():
            raise BundleError('Release App artifact missing')
        # A Chinese/space-bearing installation path, unrelated to the build checkout.
        relocated = work/'移动 安装目录'
        relocated.mkdir()
        app = relocated/'诡秘世界.app'
        shutil.copytree(original,app,symlinks=True)
        runtime = app/'Contents/Resources/LocalEngine'
        manifest = stage_engine(runtime,logs)
        sign_bundle(app,logs)
        before = source_inventory(app)
        transport = packaged_probe(app,work,logs)
        actual_app = release_app_probe(app,logs)
        if source_inventory(app) != before:
            raise BundleError('Launching modified the signed application bundle')
        run(['codesign','--verify','--deep','--strict','--verbose=2',str(app)],
            cwd=ROOT,log=logs/'post-launch-codesign.log')
        archive = output/'WorldofMysteries-arm64-development.zip'
        run(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(app),str(archive)],
            cwd=ROOT,log=logs/'archive.log')
        report = {'format_version':1,'source_commit':manifest['source_commit'],
            'artifact':archive.name,'artifact_sha256':sha256(archive),'artifact_size':archive.stat().st_size,
            'signature':'ad-hoc','hardened_runtime':True,'sandbox':True,'helper_inherits_sandbox':True,
            'notarized':False,'gate_package':'not-accepted','runtime_archive_sha256':manifest['runtime_archive_sha256'],
            'python_version':manifest['python_version'],'agentscope_version':manifest['agentscope_version'],
            'dependency_lock_sha256':manifest['dependency_lock_sha256'],
            'transport_probe':transport,'release_app_probe':actual_app,'bundle_unchanged_after_launch':True,
            'remaining_acceptance':['Developer ID signing and notarization','target-user installation and performance acceptance',
                                    'persistent-world database and upgrade acceptance']}
        (output/'package-evidence.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        (output/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        build(args.output.resolve())
    except (BundleError,OSError,subprocess.TimeoutExpired,ValueError) as exc:
        print(f'Packaging failed ({type(exc).__name__}): {exc}',file=sys.stderr)
        raise SystemExit(1)
