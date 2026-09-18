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
