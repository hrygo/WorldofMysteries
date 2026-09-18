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
