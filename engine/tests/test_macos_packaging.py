"""Packaging checks supplement, never replace, existing FULL_P0 checks."""
import json
from pathlib import Path
import plistlib
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_macos_package as package


@pytest.mark.parametrize('dependency',['@rpath/libpython3.14.dylib','@loader_path/../lib/libpython.dylib',
    '@executable_path/../lib/libpython.dylib','/usr/lib/libSystem.B.dylib',
    '/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation'])
def test_only_relocatable_or_os_libraries_accepted(dependency):
    package.validate_load_paths('binary:\n\t'+dependency+' (compatibility version 1.0.0)\n')


@pytest.mark.parametrize('dependency',['/opt/homebrew/lib/python.dylib','/Library/Frameworks/Python.framework/Python',
    '/tmp/build/libpython.dylib','../some/library.dylib','libpython.dylib'])
def test_host_specific_dependencies_rejected(dependency):
    with pytest.raises(package.BundleError): package.validate_load_paths('binary:\n\t'+dependency+' (compatibility version 1.0)\n')


def test_macho_detection_ignores_symlinks(tmp_path):
    (tmp_path/'exe').write_bytes(b'\xcf\xfa\xed\xfecontents')
    (tmp_path/'data').write_text('not a binary')
    (tmp_path/'link').symlink_to('exe')
    assert package.macho_files(tmp_path) == [tmp_path/'exe']


def test_entitlements_preserve_sandbox_and_do_not_disable_validation():
    app=plistlib.loads((ROOT/'macos-app/Packaging/App.entitlements').read_bytes())
    engine=plistlib.loads((ROOT/'macos-app/Packaging/Engine.entitlements').read_bytes())
    assert app == {'com.apple.security.app-sandbox':True,'com.apple.security.network.client':True,
                   'com.apple.security.files.user-selected.read-only':True}
    assert engine == {'com.apple.security.app-sandbox':True,'com.apple.security.inherit':True}


def test_runtime_launch_does_not_write_bytecode_or_use_host_environment():
    source=(ROOT/'macos-app/WorldOfMysteries/EngineProcessManager.swift').read_text()
    assert '["-E", "-s", "-B", "-X", "utf8", "-m"' in source
    assert 'runtime-manifest.json' in source
    assert '.resolvingSymlinksInPath()' in source


def test_additive_packaging_gate_and_full_gate_are_separate():
    full=json.loads((ROOT/'.hacf/gates/full_p0.json').read_text())
    additional=json.loads((ROOT/'.hacf/gates/bundled_runtime_p0.json').read_text())
    assert len(full['stages']) == 4
    assert additional['gate_profile_id'] == 'BUNDLED_RUNTIME_P0'
    assert additional['stages'][0]['command'] == ['python3','scripts/build_macos_package.py','--output','.hacf/artifacts/bundled-runtime']
    assert 'not Developer ID' in additional['description']


def test_non_macos_build_cannot_touch_output(tmp_path,monkeypatch):
    monkeypatch.setattr(package.sys,'platform','linux')
    with pytest.raises(package.BundleError): package.build(tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_probe_clears_build_tools_from_environment(monkeypatch):
    monkeypatch.setenv('PATH','/opt/developer/bin')
    monkeypatch.setenv('DYLD_LIBRARY_PATH','/bad-libraries')
    env=package.minimal_environment()
    assert '/opt/' not in env['PATH'] and 'DYLD_LIBRARY_PATH' not in env
    assert env['PYTHONHOME'].startswith('/nonexistent-')


def test_dependency_probe_uses_the_locked_sdk_message_api():
    source = (ROOT/'scripts/bundle_engine.py').read_text()
    assert 'agentscope.init(' not in source
    assert 'from agentscope.message import UserMsg' in source
    assert "get_text_content() == 'offline'" in source
    signing = (ROOT/'scripts/build_macos_package.py').read_text()
    assert "['otool', '-arch', 'arm64', '-L'" in signing


@pytest.mark.parametrize('identity', ['libitcl4.3.8.dylib', '/build/own-id.dylib'])
def test_dylib_own_identity_is_not_a_loaded_dependency(identity):
    package.validate_load_paths('binary:\n\t'+identity+' (compatibility version 1.0)\n'
        '\t/usr/lib/libSystem.B.dylib (compatibility version 1.0)\n',
        identification='binary:\n'+identity+'\n')


def test_identity_does_not_exempt_a_real_external_dependency():
    with pytest.raises(package.BundleError):
        package.validate_load_paths('binary:\nlibself.dylib (compatibility version 1.0)\n'
            '/opt/homebrew/lib/libbad.dylib (compatibility version 1.0)\n',
            identification='binary:\nlibself.dylib\n')


def test_mismatching_native_identity_fails_closed():
    with pytest.raises(package.BundleError):
        package.validate_load_paths('binary:\n/opt/homebrew/bad.dylib (compatibility version 1.0)\n',
            identification='binary:\nlibself.dylib\n')


def test_signing_preserves_helper_entitlements_through_parent_path_alias(tmp_path, monkeypatch):
    actual = tmp_path/'actual'; actual.mkdir()
    alias = tmp_path/'alias'; alias.symlink_to(actual, target_is_directory=True)
    app = alias/'Example.app'
    interpreter = app/'Contents/Resources/LocalEngine/bin/python3'
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b'\xcf\xfa\xed\xfecontents')
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == 'otool':
            return 'binary:\n' + ('\t/usr/lib/libSystem.B.dylib (compatibility version 1.0)\n' if '-L' in command else '')
        if command[0] == 'lipo': return 'arm64'
        if '-dvv' in command: return 'flags=0x10000(runtime)'
        if '-d' in command and '--entitlements' in command:
            name = 'Engine.entitlements' if Path(command[-1]).is_file() else 'App.entitlements'
            return (ROOT/'macos-app/Packaging'/name).read_text()
        return ''
    monkeypatch.setattr(package, 'run', fake_run)
    package.sign_bundle(app, tmp_path/'logs')
    signs = [c for c in calls if c[0]=='codesign' and '--force' in c and Path(c[-1]).is_file()]
    assert len(signs) == 1
    assert '--entitlements' in signs[0]
    assert signs[0][signs[0].index('--entitlements')+1].endswith('/Engine.entitlements')


def test_runtime_setup_diagnostics_preserve_user_safe_errors():
    source = (ROOT/'macos-app/WorldOfMysteries/EngineProcessManager.swift').read_text()
    assert 'Logger(subsystem: "dev.worldofmysteries", category: "EngineRuntime")' in source
    assert 'throw rejected("socket-path-budget", code: Int32(socketBytes))' in source
    logging = source.split('private static func rejected(', 1)[1].split('static func create(', 1)[0]
    assert 'return .invalidConfiguration' in logging
    assert 'token' not in logging and 'directory.path' not in logging and 'environment' not in logging


def test_failed_diagnostic_collection_cannot_hide_app_failure(tmp_path, monkeypatch):
    class App:
        pid = 123
        def __init__(self): self.stopped = False
        def poll(self): return -9 if self.stopped else None
        def kill(self): self.stopped = True
        def wait(self, **kwargs): return -9
    app = App()
    monkeypatch.setattr(package.subprocess, 'Popen', lambda *a, **k: app)
    def original_failure(*a, **k): raise package.BundleError('original launch failure')
    monkeypatch.setattr(package, 'await_engine', original_failure)
    def diagnostics_fail(*a, **k): raise package.BundleError('diagnostic unavailable')
    monkeypatch.setattr(package, 'run', diagnostics_fail)
    with pytest.raises(package.BundleError, match='original launch failure'):
        package.release_app_probe(tmp_path/'App.app', tmp_path)
    assert app.stopped


def test_process_ancestry_never_parses_display_escaped_arguments(monkeypatch):
    calls = []
    def read(command, **kwargs):
        calls.append(command)
        return '   201  100\n  202 201\n 203 100\n'
    monkeypatch.setattr(package.subprocess, 'check_output', read)
    assert package.children(100) == [201, 203]
    assert calls == [['/bin/ps', '-axo', 'pid=,ppid=']]


@pytest.mark.parametrize('raw', ['123 invalid', '123 4 extra', 'oops', '123 -1'])
def test_invalid_ancestry_is_not_treated_as_no_engine(raw, monkeypatch):
    monkeypatch.setattr(package.subprocess, 'check_output', lambda *a, **kw: raw)
    with pytest.raises(package.BundleError, match='ancestry'):
        package.children(4)


def test_executable_identity_accepts_unicode_paths_and_aliases(tmp_path, monkeypatch):
    app = tmp_path/'安装 空格'/'诡秘世界.app'
    binary = app/'Contents/Resources/LocalEngine/bin/python3'
    binary.parent.mkdir(parents=True)
    real = binary.with_name('python3.14'); real.write_bytes(b'owned executable')
    binary.symlink_to('python3.14')
    alias = tmp_path/'alias'; alias.symlink_to(app, target_is_directory=True)
    monkeypatch.setattr(package, 'process_executable', lambda pid: alias/'Contents/Resources/LocalEngine/bin/python3.14')
    assert package.is_bundled_engine(123, app)
    unrelated = tmp_path/'another-python'; unrelated.write_bytes(real.read_bytes())
    monkeypatch.setattr(package, 'process_executable', lambda pid: unrelated)
    assert not package.is_bundled_engine(123, app)
    monkeypatch.setattr(package, 'process_executable', lambda pid: None)
    assert not package.is_bundled_engine(123, app)


def test_kernel_process_path_returns_unescaped_filesystem_bytes(tmp_path, monkeypatch):
    raw = bytes(tmp_path/'诡秘 空格.app'/'python3')
    def kernel(pid, buffer, size):
        assert pid == 123 and size == 4096
        buffer.value = raw
        return len(raw)
    monkeypatch.setattr(package, '_process_path_function', lambda: kernel)
    assert package.process_executable(123) == Path(raw.decode())


@pytest.mark.parametrize('gone', [True, False])
def test_kernel_path_failure_distinguishes_exit_and_missing_access(gone, monkeypatch):
    def kernel(*args):
        package.ctypes.set_errno(package.errno.EPERM)
        return 0
    monkeypatch.setattr(package, '_process_path_function', lambda: kernel)
    monkeypatch.setattr(package, 'process_exists', lambda pid: not gone)
    if gone:
        assert package.process_executable(123) is None
    else:
        with pytest.raises(package.BundleError, match='identity unavailable'):
            package.process_executable(123)


@pytest.mark.parametrize('value,length', [(b'', 1), (b'relative', 8), (b'/truncated', 4096)])
def test_invalid_kernel_path_is_rejected(value, length, monkeypatch):
    def kernel(pid, buffer, size):
        buffer.value = value
        return length
    monkeypatch.setattr(package, '_process_path_function', lambda: kernel)
    with pytest.raises(package.BundleError, match='Invalid kernel'):
        package.process_executable(123)


def test_await_engine_requires_direct_parent_and_exact_executable(tmp_path, monkeypatch):
    class App:
        pid = 100
        def poll(self): return None
    monkeypatch.setattr(package, 'children', lambda pid: [101, 102])
    monkeypatch.setattr(package, 'is_bundled_engine', lambda pid, app: pid == 102)
    assert package.await_engine(App(), tmp_path) == 102
    monkeypatch.setattr(package, 'is_bundled_engine', lambda pid, app: True)
    assert package.await_engine(App(), tmp_path, previous=101) == 102
    with pytest.raises(package.BundleError, match='duplicate'):
        package.await_engine(App(), tmp_path)


@pytest.mark.skipif(sys.platform != 'darwin', reason='Darwin kernel process identity')
def test_actual_macos_kernel_executable_identity():
    import os
    assert package.process_executable(os.getpid()).samefile(sys.executable)
