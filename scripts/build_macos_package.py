#!/usr/bin/env python3
"""Build a real bundled-engine Release artifact and collect ad-hoc engineering evidence.

No certificate/password is read or exported. Ad-hoc signing exercises the Sandbox
and Hardened Runtime only; this is never labelled a notarized distribution build.
The release binary is not replaced by a test double. A separate disposable copy
hosts a probe built from the same production Swift process/transport sources.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
from functools import lru_cache
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

PACKAGE_PROBE_SWIFT_SOURCES = (
    'IPCEnvelope',
    'IPCFrameCodec',
    'EngineRuntimeModels',
    'EngineSocketTransport',
    'MediaProtocol',
    'EngineIPCClient',
    'EngineProcessManager',
)


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


def children(pid: int) -> list[int]:
    # ps command/args are display-escaped (strvis on Darwin), not filesystem
    # paths. Read only numeric ancestry here; executable identity comes from
    # the kernel. Neither user arguments nor environment are collected.
    raw = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid='], text=True, timeout=5)
    result = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2 or not all(item.isdecimal() for item in parts):
            raise BundleError('Invalid numeric process ancestry response')
        if int(parts[1]) == pid:
            result.append(int(parts[0]))
    return result


@lru_cache(maxsize=1)
def _process_path_function():
    if sys.platform != 'darwin':
        raise BundleError('Kernel process identity requires macOS')
    function = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True).proc_pidpath
    function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    function.restype = ctypes.c_int
    return function


def process_executable(pid: int) -> Path | None:
    # PROC_PIDPATHINFO_MAXSIZE is four MAXPATHLEN blocks on Darwin. This is
    # build-host observation only; no private API is linked into the App.
    buffer = ctypes.create_string_buffer(4096)
    ctypes.set_errno(0)
    length = _process_path_function()(pid, buffer, len(buffer))
    if length <= 0:
        code = ctypes.get_errno()
        if code == errno.ESRCH or not process_exists(pid):
            return None  # The child exited between ancestry and path reads.
        raise BundleError(f'Kernel executable identity unavailable (code {code})')
    value = buffer.value
    if length >= len(buffer) or not value or not value.startswith(b'/'):
        raise BundleError('Invalid kernel executable identity')
    return Path(os.fsdecode(value))


def _same_executable(pid: int, executable: Path) -> bool:
    observed = process_executable(pid)
    if observed is None:
        return False
    try:
        return observed.samefile(executable)
    except FileNotFoundError:
        return False


def is_bundled_engine(pid: int, bundle: Path) -> bool:
    return _same_executable(pid, bundle/'Contents/Resources/LocalEngine/bin/python3')


def user_process_ids() -> list[int]:
    """Return only this uid's process IDs; executable identity is checked separately."""
    raw = subprocess.check_output(['/bin/ps', '-axo', 'pid=,uid='], text=True, timeout=5)
    uid = os.getuid()
    result = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2 or not all(item.isdecimal() for item in parts):
            raise BundleError('Invalid numeric process identity response')
        if int(parts[1]) == uid:
            result.append(int(parts[0]))
    return result


def bundle_app_pids(bundle: Path) -> list[int]:
    """Find this exact bundle copy using kernel executable identity, never argv text."""
    executable = bundle/'Contents/MacOS/WorldOfMysteries'
    return [pid for pid in user_process_ids() if _same_executable(pid, executable)]


def await_app_launch(
    launcher: subprocess.Popen,
    bundle: Path,
    *,
    preexisting: set[int],
) -> int:
    end = time.monotonic() + 20
    while time.monotonic() < end:
        candidates = [pid for pid in bundle_app_pids(bundle) if pid not in preexisting]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise BundleError('LaunchServices created duplicate Release App instances')
        if launcher.poll() is not None:
            raise BundleError('LaunchServices exited before the Release App became observable')
        time.sleep(0.1)
    raise BundleError('LaunchServices did not make the Release App observable')


def launch_release_app(bundle: Path, log) -> tuple[subprocess.Popen, int]:
    """Launch the product bundle through LaunchServices and bind its exact process identity."""
    preexisting = set(bundle_app_pids(bundle))
    launcher = subprocess.Popen(
        ['/usr/bin/open', '-n', '-W', '-F', str(bundle)],
        stdout=log,
        stderr=log,
    )
    try:
        return launcher, await_app_launch(launcher, bundle, preexisting=preexisting)
    except Exception:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=5)
        raise


def await_engine(app_pid: int, bundle: Path, *, previous: int | None = None) -> int:
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if not process_exists(app_pid) or not _same_executable(
            app_pid, bundle/'Contents/MacOS/WorldOfMysteries'
        ):
            raise BundleError('Release App exited before Engine startup')
        candidates = [pid for pid in children(app_pid)
                      if pid != previous and is_bundled_engine(pid, bundle)]
        if len(candidates) == 1:
            return candidates[0]
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


def _release_observation(app_pid: int | None, bundle: Path) -> dict[str, object]:
    if app_pid is None:
        return {'app_observed': False}
    alive = process_exists(app_pid)
    exact_app = alive and _same_executable(
        app_pid, bundle/'Contents/MacOS/WorldOfMysteries'
    )
    direct = children(app_pid) if exact_app else []
    engines = [pid for pid in direct if is_bundled_engine(pid, bundle)]
    return {
        'app_observed': True,
        'app_alive': alive,
        'app_identity_exact': exact_app,
        'direct_child_count': len(direct),
        'bundled_engine_child_count': len(engines),
    }


def release_app_probe(bundle: Path, logs: Path) -> dict:
    started = time.monotonic()
    known_children: list[int] = []
    launcher: subprocess.Popen | None = None
    app_pid: int | None = None
    with (logs/'release-app.log').open('wb') as log:
        try:
            launcher, app_pid = launch_release_app(bundle, log)
            first = await_engine(app_pid, bundle)
            known_children.append(first)
            spawned_ms = (time.monotonic() - started) * 1000
            # Wait for the App to finish its normal handshake and attach recovery.
            time.sleep(2)
            if not process_exists(first):
                raise BundleError('Bundled Engine exited after spawn')
            if first not in children(app_pid) or not is_bundled_engine(first, bundle):
                raise BundleError('Engine identity changed before crash probe')
            os.kill(first, signal.SIGKILL)
            second = await_engine(app_pid, bundle, previous=first)
            known_children.append(second)
            time.sleep(2)
            if not process_exists(second):
                raise BundleError('Recovered bundled Engine exited')
            # Force-quit the exact App process. The LaunchServices waiter must
            # then return and the child Engine must observe parent death.
            if not _same_executable(app_pid, bundle/'Contents/MacOS/WorldOfMysteries'):
                raise BundleError('Release App identity changed before force-quit probe')
            os.kill(app_pid, signal.SIGKILL)
            if launcher is not None:
                launcher.wait(timeout=5)
            deadline = time.monotonic() + 6
            while process_exists(second) and time.monotonic() < deadline:
                time.sleep(0.1)
            if process_exists(second):
                raise BundleError('Engine outlived the force-quit Release App')
            return {'release_app_started': True, 'engine_spawn_ms': spawned_ms,
                    'engine_crash_recovered': True, 'app_force_quit_cleaned_engine': True,
                    'launch_mode': 'launchservices',
                    'process_identity': 'kernel executable file identity and direct parent',
                    'ui_interactive_acceptance': 'not-tested'}
        except Exception:
            # Keep diagnostics bounded and free of paths, argv, environment,
            # credentials or payloads while distinguishing launch/lifecycle
            # observation from Engine-child observation.
            try:
                (logs/'release-process-observation.json').write_text(
                    json.dumps(_release_observation(app_pid, bundle), sort_keys=True) + '\n'
                )
            except (BundleError, OSError):
                pass
            try:
                run(['/usr/bin/log', 'show', '--last', '1m', '--style', 'compact',
                     '--predicate', 'subsystem == "dev.worldofmysteries"'], cwd=ROOT,
                    log=logs/'release-runtime-diagnostic.log', timeout=10)
            except (BundleError, OSError):
                pass  # The original launch failure remains authoritative.
            raise
        finally:
            if app_pid is not None and process_exists(app_pid):
                try:
                    if _same_executable(app_pid, bundle/'Contents/MacOS/WorldOfMysteries'):
                        os.kill(app_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if launcher is not None and launcher.poll() is None:
                launcher.kill()
                launcher.wait(timeout=5)
            for pid in known_children:
                # Only children spawned by this probe are eligible for cleanup.
                try:
                    if is_bundled_engine(pid, bundle):
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def packaged_probe(bundle: Path, work: Path, logs: Path) -> dict:
    probe = work/'Probe.app'
    shutil.copytree(bundle, probe, symlinks=True)
    swift = ROOT/'macos-app/WorldOfMysteries'
    names = PACKAGE_PROBE_SWIFT_SOURCES
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
            'data_sqlite_version':manifest['data_sqlite']['sqlite_version'],
            'data_sqlite_module':manifest['data_sqlite']['module'],
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
