"""Host-independent regression coverage for the production runtime producer."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import bundle_engine as bundler
import build_macos_package as package_builder


def make_archive(tmp_path, items):
    archive = tmp_path/'runtime.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, kind, content in items:
            member = tarfile.TarInfo(name)
            member.type = kind
            if kind == tarfile.REGTYPE:
                member.size = len(content)
                tar.addfile(member, io.BytesIO(content))
            else:
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    member.linkname = content
                tar.addfile(member)
    lock = {'sha256': bundler.sha256(archive), 'size': archive.stat().st_size}
    return archive, lock


def test_upstream_lock_is_fixed_and_gil_enabled():
    lock = bundler.read_lock()
    assert lock['python_version'] == '3.14.7'
    assert lock['gil_enabled'] is True
    assert 'freethreaded' not in lock['filename']
    assert len(lock['sha256']) == 64
    assert lock['release'] in lock['url']


@pytest.mark.parametrize('field,value', [('gil_enabled',1),('gil_enabled',False),('architecture','x86_64'),
    ('python_version','3.14.8'),('platform','linux'),('format_version',True),('size',True),('size',0),
    ('sha256','0'*63),('release','latest'),('url','http://github.com/evil'),
    ('url','https://github.com.evil.invalid/asset')])
def test_invalid_locks_rejected(tmp_path, field, value):
    lock = bundler.read_lock()
    lock[field] = value
    file = tmp_path/'lock.json'
    file.write_text(json.dumps(lock))
    with pytest.raises(bundler.BundleError): bundler.read_lock(file)


def test_safe_relative_symlink_and_file_are_preserved(tmp_path):
    archive, lock = make_archive(tmp_path,[('python/bin/python3.14',tarfile.REGTYPE,b'python'),
        ('python/bin/python3',tarfile.SYMTYPE,'python3.14')])
    root = bundler.extract_runtime(archive,tmp_path/'out',lock)
    assert (root/'bin/python3').is_symlink()
    assert (root/'bin/python3').read_bytes() == b'python'


@pytest.mark.parametrize('name,kind,content', [('../escape',tarfile.REGTYPE,b'x'),
    ('/absolute',tarfile.REGTYPE,b'x'),('other/bin/a',tarfile.REGTYPE,b'x'),
    ('python/../escape',tarfile.REGTYPE,b'x'),('python/fifo',tarfile.FIFOTYPE,''),
    ('python/link',tarfile.SYMTYPE,'/etc/passwd'),('python/link',tarfile.SYMTYPE,'../../escape'),
    ('python/link',tarfile.LNKTYPE,'../../escape')])
def test_unsafe_archives_rejected(tmp_path,name,kind,content):
    archive,lock = make_archive(tmp_path,[(name,kind,content)])
    with pytest.raises((bundler.BundleError,tarfile.FilterError,KeyError)):
        bundler.extract_runtime(archive,tmp_path/'out',lock)
    assert not (tmp_path/'escape').exists()


def test_duplicate_archive_members_rejected(tmp_path):
    archive,lock = make_archive(tmp_path,[('python/a',tarfile.REGTYPE,b'a'),('python/a',tarfile.REGTYPE,b'b')])
    with pytest.raises(bundler.BundleError): bundler.extract_runtime(archive,tmp_path/'out',lock)


def test_hash_is_checked_before_extraction(tmp_path):
    archive,lock = make_archive(tmp_path,[('python/a',tarfile.REGTYPE,b'a')])
    lock['sha256'] = '0'*64
    with pytest.raises(bundler.BundleError): bundler.extract_runtime(archive,tmp_path/'out',lock)
    assert not (tmp_path/'out').exists()


def test_size_is_checked_before_extraction(tmp_path):
    archive,lock = make_archive(tmp_path,[('python/a',tarfile.REGTYPE,b'a')])
    lock['size'] += 1
    with pytest.raises(bundler.BundleError): bundler.extract_runtime(archive,tmp_path/'out',lock)
    assert not (tmp_path/'out').exists()


def test_existing_output_is_not_replaced(tmp_path):
    archive,lock = make_archive(tmp_path,[('python/a',tarfile.REGTYPE,b'a')])
    output=tmp_path/'out'; output.mkdir(); (output/'keep').write_text('data')
    with pytest.raises(FileExistsError): bundler.extract_runtime(archive,output,lock)
    assert (output/'keep').read_text() == 'data'


@pytest.mark.parametrize('target', ['../external','missing','/etc/passwd'])
def test_escaped_or_dangling_filesystem_links_rejected(tmp_path,target):
    root=tmp_path/'runtime'; root.mkdir()
    (tmp_path/'external').write_text('not packaged')
    (root/'link').symlink_to(target)
    with pytest.raises(bundler.BundleError): bundler.validate_links(root)


def test_inventory_is_relative_and_does_not_read_symlink_target(tmp_path):
    root=tmp_path/'runtime'; root.mkdir(); (root/'a').write_bytes(b'a')
    (root/'link').symlink_to('a')
    assert bundler.source_inventory(root) == {'a':hashlib.sha256(b'a').hexdigest()}


def test_foreign_platform_cannot_build_or_claim_success(tmp_path,monkeypatch):
    monkeypatch.setattr(bundler.sys,'platform','linux')
    with pytest.raises(bundler.BundleError): bundler.stage_engine(tmp_path/'new',tmp_path/'logs')
    assert not (tmp_path/'new').exists()


@pytest.mark.parametrize('value', [None, [], 1, 'bad'])
def test_lock_root_must_be_an_object(tmp_path, value):
    path = tmp_path / 'lock.json'
    path.write_text(json.dumps(value))
    with pytest.raises(bundler.BundleError):
        bundler.read_lock(path)


class DownloadResponse(io.BytesIO):
    def geturl(self):
        return 'https://release-assets.githubusercontent.com/pinned-asset'


def download_case(tmp_path, monkeypatch, outcomes):
    body = b'pinned runtime archive'
    lock = {'url': 'https://github.com/pinned-asset', 'size': len(body),
            'sha256': hashlib.sha256(body).hexdigest()}
    calls, sleeps = [], []
    def open_response(request, timeout):
        calls.append((request.full_url, timeout))
        outcome = outcomes[min(len(calls)-1, len(outcomes)-1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome() if callable(outcome) else DownloadResponse(outcome)
    monkeypatch.setattr(bundler.urllib.request, 'urlopen', open_response)
    monkeypatch.setattr(bundler.time, 'sleep', sleeps.append)
    return lock, tmp_path/'runtime.tar.gz', body, calls, sleeps


def test_transient_download_retries_same_pin_and_publishes_only_verified_archive(tmp_path, monkeypatch):
    error = bundler.urllib.error.HTTPError('https://private-url',504,'gateway',{},io.BytesIO(b'secret body'))
    body = b'pinned runtime archive'
    lock,target,_,calls,sleeps = download_case(tmp_path,monkeypatch,[error,body])
    bundler.download_runtime(lock,target)
    assert target.read_bytes() == body
    assert calls == [(lock['url'],60)]*2 and sleeps == [1]
    assert list(tmp_path.iterdir()) == [target]
    assert error.fp.closed


@pytest.mark.parametrize('failure', [TimeoutError(), ConnectionResetError(),
    bundler.urllib.error.URLError(TimeoutError())])
def test_partial_download_is_removed_before_retry(tmp_path,monkeypatch,failure):
    class Interrupted(DownloadResponse):
        def read(self, size=-1):
            if self.tell(): raise failure
            return super().read(3)
    body = b'pinned runtime archive'
    lock,target,_,calls,_ = download_case(tmp_path,monkeypatch,[lambda:Interrupted(body),body])
    bundler.download_runtime(lock,target)
    assert target.read_bytes() == body and len(calls) == 2
    assert list(tmp_path.iterdir()) == [target]


def test_truncated_response_is_retried_without_retaining_partial_bytes(tmp_path,monkeypatch):
    body = b'pinned runtime archive'
    lock,target,_,calls,_ = download_case(tmp_path,monkeypatch,[body[:3],body])
    bundler.download_runtime(lock,target)
    assert target.read_bytes() == body and len(calls) == 2
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('status', [408,429,500,502,503,504])
def test_retry_exhaustion_is_bounded_and_leaves_no_archive(tmp_path,monkeypatch,status):
    def failure():
        raise bundler.urllib.error.HTTPError('https://private-url',status,'secret',{},None)
    lock,target,_,calls,sleeps = download_case(tmp_path,monkeypatch,[failure])
    with pytest.raises(bundler.BundleError,match='exhausted 3 attempts') as error:
        bundler.download_runtime(lock,target)
    assert len(calls) == 3 and sleeps == [1,2]
    assert not list(tmp_path.iterdir())
    assert 'private-url' not in str(error.value) and 'secret' not in str(error.value)


@pytest.mark.parametrize('failure', [
    bundler.urllib.error.HTTPError('https://private-url',404,'secret',{},None),
    bundler.urllib.error.HTTPError('https://private-url',403,'secret',{},None),
    bundler.urllib.error.URLError('certificate validation failed')])
def test_permanent_download_failures_are_not_retried(tmp_path,monkeypatch,failure):
    lock,target,_,calls,sleeps = download_case(tmp_path,monkeypatch,[failure])
    with pytest.raises(bundler.BundleError): bundler.download_runtime(lock,target)
    assert len(calls) == 1 and not sleeps and not list(tmp_path.iterdir())


@pytest.mark.parametrize('variant', ['digest','oversize','insecure-redirect'])
def test_download_integrity_failure_never_retries_or_publishes(tmp_path,monkeypatch,variant):
    body = b'pinned runtime archive'
    class Insecure(DownloadResponse):
        def geturl(self): return 'http://insecure.invalid'
    outcome = body + b'extra' if variant == 'oversize' else body
    if variant == 'insecure-redirect': outcome = lambda:Insecure(body)
    lock,target,_,calls,sleeps = download_case(tmp_path,monkeypatch,[outcome])
    if variant == 'digest': lock['sha256'] = '0'*64
    with pytest.raises(bundler.BundleError): bundler.download_runtime(lock,target)
    assert len(calls) == 1 and not sleeps and not list(tmp_path.iterdir())


@pytest.mark.parametrize('symlink', [False, True])
def test_download_preserves_existing_output_without_network(tmp_path,monkeypatch,symlink):
    lock,target,_,calls,_ = download_case(tmp_path,monkeypatch,[b'ignored'])
    if symlink: target.symlink_to('missing')
    else: target.write_bytes(b'keep')
    with pytest.raises(bundler.BundleError): bundler.download_runtime(lock,target)
    assert not calls
    assert target.is_symlink() if symlink else target.read_bytes() == b'keep'


def test_download_publish_race_cannot_overwrite_another_builder(tmp_path,monkeypatch):
    body = b'pinned runtime archive'
    target = tmp_path/'runtime.tar.gz'
    def competing_response():
        target.write_bytes(b'other builder')
        return DownloadResponse(body)
    lock,target,_,calls,_ = download_case(tmp_path,monkeypatch,[competing_response])
    with pytest.raises(FileExistsError): bundler.download_runtime(lock,target)
    assert target.read_bytes() == b'other builder'
    assert list(tmp_path.iterdir()) == [target] and len(calls) == 1


def test_runtime_stager_requires_private_data_sqlite_probe():
    source = (Path(__file__).resolve().parents[2]/'scripts/bundle_engine.py').read_text()
    assert 'stage_data_sqlite(runtime, logs, env=env)' in source
    assert "_wom_sqlite3.sqlite_version == '3.53.4'" in source
    assert "'data_sqlite': data_sqlite" in source


def test_packaged_probe_source_closure_tracks_media_protocol_dependency():
    names = package_builder.PACKAGE_PROBE_SWIFT_SOURCES
    required = {
        "IPCEnvelope",
        "IPCFrameCodec",
        "EngineRuntimeModels",
        "EngineSocketTransport",
        "MediaProtocol",
        "EngineIPCClient",
        "EngineProcessManager",
    }
    assert set(names) == required
    assert names.index("MediaProtocol") < names.index("EngineIPCClient")
    swift_root = ROOT / "macos-app" / "WorldOfMysteries"
    assert all((swift_root / f"{name}.swift").is_file() for name in names)
