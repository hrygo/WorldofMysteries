"""Render evidence summaries, including empty/error branches, through real Markdown.

markdown-it-py is already present in the locked dependency graph (via Rich).
Do not replace these assertions with a search for pipe characters: the original
regression contained pipes but rendered no receipt table at all.
"""
from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import generate_pr_report as reporter


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self.tables[-1].append([])
        elif tag in ("td", "th"):
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.tables[-1][-1].append("".join(self.cell))
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def rendered(text):
    html = MarkdownIt("commonmark").enable("table").render(text)
    parser = Tables()
    parser.feed(html)
    return html, parser.tables


def receipt_table(text):
    section = text.split("### 本 PR 携带的凭单 (Receipts)", 1)[1].split("\n### ", 1)[0]
    _, tables = rendered(section)
    assert len(tables) == 1, "Every receipt state must render one real HTML table"
    table = tables[0]
    assert len(table) >= 2, "Header, delimiter and a data/empty-state row are required"
    assert len(table[0]) == 6
    assert all(len(row) == len(table[0]) for row in table)
    return table


@pytest.fixture
def records(tmp_path, monkeypatch):
    changed = []
    monkeypatch.setattr(reporter, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reporter, "detect_changed_files", lambda: (changed, []))
    for key in ("GITHUB_ACTOR", "GITHUB_HEAD_REF", "WOM_REPORT_HEAD_SHA", "WOM_REPORT_BASE_SHA"):
        monkeypatch.delenv(key, raising=False)

    def add(path, value, *, changed_file=True):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        if changed_file:
            changed.append(path)
        return target

    return add, changed


def capsule(task="T1", **kw):
    return dict(task_id=task, capsule_id="CAP-" + task, capsule_revision=1,
                title="Evidence test", assigned_role="AGT-ARB", risk_class="high",
                base={"target_ref": "main", "target_sha": "a" * 40},
                gates={"profile": "FULL_P0", "profile_digest": "sha256:" + "b" * 64}, **kw)


def receipt(task="T1", verdict="passed", **kw):
    return dict(task_id=task, receipt_type="work", head_commit="c" * 40,
                verdict=verdict, gate_profile_digest="sha256:" + "b" * 64,
                coverage_gaps=[], **kw)


def test_empty_receipts_keep_a_rendered_table(records):
    add, _ = records
    add(".agents/capsules/T1.json", capsule())
    report = reporter.generate_report()
    table = receipt_table(report)
    assert "未找到凭单" in str(table)
    assert "尚未生成" not in report, "Repository absence is not proof of non-execution"
    assert "不代表测试通过" in report


@pytest.mark.parametrize("verdict", ["passed", "failed"])
def test_receipts_with_and_without_capsules(records, verdict):
    add, _ = records
    add(".agents/receipts/T1/abc.json", receipt(verdict=verdict))
    table = receipt_table(reporter.generate_report())
    assert verdict in str(table)
    assert ".agents/receipts/T1/abc.json" in str(table)


def test_all_capsules_and_their_unchanged_receipts_are_reported(records):
    add, _ = records
    for task in ("T2", "T1"):
        add(f".agents/capsules/{task}.json", capsule(task))
        add(f".agents/receipts/{task}/abc.json", receipt(task), changed_file=False)
    report = reporter.generate_report()
    assert "CAP-T1" in report and "CAP-T2" in report
    assert len(receipt_table(report)) == 3


def test_receipts_are_deduplicated_by_path(records):
    add, _ = records
    add(".agents/capsules/T1.json", capsule())
    add(".agents/receipts/T1/abc.json", receipt())
    assert len(receipt_table(reporter.generate_report())) == 2


@pytest.mark.parametrize("bad", [None, [], 1, "text", {"task_id": "T1"},
                                 {**receipt(), "coverage_gaps": None},
                                 {**receipt(), "coverage_gaps": "not a list"},
                                 {**receipt(), "coverage_gaps": [None]},
                                 {**receipt(), "verdict": "invented"},
                                 {**receipt(), "head_commit": []}])
def test_invalid_receipts_are_diagnosed_not_silently_lost(records, bad):
    add, _ = records
    add(".agents/receipts/T1/bad.json", bad)
    report = reporter.generate_report()
    assert "读取失败" in report
    assert "bad.json" in report
    assert "无覆盖缺口记录" not in report
    assert "尚未生成" not in report
    receipt_table(report)


@pytest.mark.parametrize("raw", [b"{", b"\xff", b'{"task_id":"T1","task_id":"T2"}',
                                 b'{"task_id":"T1","verdict":NaN}'])
def test_bad_json_and_encoding_are_reported_without_payload_echo(records, raw):
    add, _ = records
    path = add(".agents/receipts/T1/bad.json", receipt())
    path.write_bytes(raw)
    report = reporter.generate_report()
    assert "读取失败" in report and "bad.json" in report
    receipt_table(report)


def test_partial_receipt_failure_keeps_valid_evidence_and_diagnostic(records):
    add, _ = records
    add(".agents/receipts/T1/good.json", receipt())
    add(".agents/receipts/T1/bad.json", [])
    report = reporter.generate_report()
    assert "读取失败" in report and "good.json" in report and "bad.json" in report
    assert "无覆盖缺口记录" not in report
    receipt_table(report)


@pytest.mark.parametrize("bad", [[], None, {**capsule(), "base": []},
                                 {**capsule(), "gates": None},
                                 {**capsule(), "task_id": "../outside"}])
def test_invalid_capsule_does_not_crash_or_claim_absence(records, bad):
    add, _ = records
    add(".agents/capsules/bad.json", bad)
    report = reporter.generate_report()
    assert "读取失败" in report
    assert "未附带业务胶囊" not in report
    receipt_table(report)


def test_io_failure_is_distinguished_from_missing_receipt(records, monkeypatch):
    add, _ = records
    path = add(".agents/receipts/T1/denied.json", receipt())
    original = Path.read_text

    def read_text(self, *args, **kwargs):
        if self == path:
            raise PermissionError("sensitive host path must not be echoed")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    report = reporter.generate_report()
    assert "读取失败" in report and "denied.json" in report
    assert "sensitive host path" not in report
    receipt_table(report)


def test_symbolic_receipt_is_not_followed(records, tmp_path):
    add, changed = records
    target = add("outside.json", receipt(), changed_file=False)
    directory = tmp_path / ".agents/receipts/T1"
    directory.mkdir(parents=True)
    (directory / "linked.json").symlink_to(target)
    changed.append(".agents/receipts/T1/linked.json")
    report = reporter.generate_report()
    assert "读取失败" in report
    receipt_table(report)


def test_task_directory_must_match_receipt_identity(records):
    add, _ = records
    add(".agents/receipts/T1/wrong.json", receipt("T2"))
    report = reporter.generate_report()
    assert "读取失败" in report
    receipt_table(report)


def test_deleted_evidence_does_not_crash(records):
    _, changed = records
    changed.extend([".agents/capsules/deleted.json", ".agents/receipts/T1/deleted.json"])
    receipt_table(reporter.generate_report())


def test_dynamic_markdown_stays_in_its_cell(records):
    add, _ = records
    text = "a|b\\|c` **bold** <script>x</script>\r\n[next](bad) & end"
    c = capsule()
    c["title"] = text
    add(".agents/capsules/T1.json", c)
    r = receipt()
    r["coverage_gaps"] = [text]
    add(".agents/receipts/T1/abc.json", r)
    report = reporter.generate_report()
    html, tables = rendered(report)
    assert "<script>" not in html and 'href="bad"' not in html and "<strong>bold" not in html
    for table in tables:
        assert all(len(row) == len(table[0]) for row in table)
    assert any(text.replace("\r\n", "\n") in cell for t in tables for r in t for cell in r)
    receipt_table(report)


def test_diff_failure_remains_unknown_even_for_maintenance(records, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTOR", "dependabot[bot]")
    monkeypatch.setattr(reporter, "detect_changed_files", lambda: ([], ["diff failed"]))
    report = reporter.generate_report()
    assert "变更面判定失败" in report
    assert "免除" not in report and "尚未生成" not in report
    receipt_table(report)


def test_snapshot_uses_event_head_not_capsule_base(records, monkeypatch):
    add, _ = records
    add(".agents/capsules/T1.json", capsule())
    monkeypatch.setenv("WOM_REPORT_HEAD_SHA", "d" * 40)
    monkeypatch.setenv("WOM_REPORT_BASE_SHA", "e" * 40)
    report = reporter.generate_report()
    assert "d" * 40 in report and "e" * 40 in report
    assert "<!-- wom-evidence-summary:v1 -->" in report
    assert "<!-- wom-evidence-head:" + "d" * 40 + " -->" in report
    assert "产品验收" in report and "CI" in report


def test_missing_gap_field_is_unknown_not_zero(records):
    add, _ = records
    data = receipt()
    del data["coverage_gaps"]
    add(".agents/receipts/T1/abc.json", data)
    report = reporter.generate_report()
    assert "未记录" in str(receipt_table(report)[1][-1])
    assert "无覆盖缺口记录" not in report


def test_failed_receipt_without_gaps_still_exposes_failure(records):
    add, _ = records
    add(".agents/receipts/T1/abc.json", receipt(verdict="failed"))
    report = reporter.generate_report()
    gap_section = report.split("### 覆盖缺口", 1)[1]
    assert "failed" in gap_section


def test_format_validator_rejects_headerless_receipt_block(records):
    text = reporter.generate_report()
    reporter.validate_report_markdown(text)
    broken = text.replace("|:---|:---|:---|:---|:---|:---|\n", "")
    assert broken != text
    with pytest.raises(ValueError):
        reporter.validate_report_markdown(broken)


def test_integration_receipt_is_not_a_work_receipt(records):
    add, _ = records
    add(".agents/capsules/T1.json", capsule())
    value = receipt()
    value["receipt_type"] = "integration"
    add(".agents/receipts/T1/integration.json", value)
    report = reporter.generate_report()
    assert "integration" in str(receipt_table(report))
    assert "T1：未找到可读取的 Work Receipt" in report


def test_one_tasks_receipt_does_not_hide_another_tasks_missing_evidence(records):
    add, _ = records
    for task in ("T1", "T2"):
        add(f".agents/capsules/{task}.json", capsule(task))
    add(".agents/receipts/T1/abc.json", receipt())
    report = reporter.generate_report()
    assert "T2：未找到可读取的 Work Receipt" in report
    assert "T1：未找到可读取的 Work Receipt" not in report
    receipt_table(report)


def test_directory_read_failure_is_not_empty_history(records, monkeypatch):
    add, _ = records
    add(".agents/capsules/T1.json", capsule())
    path = add(".agents/receipts/T1/abc.json", receipt(), changed_file=False).parent
    original = Path.iterdir

    def iterdir(self):
        if self == path:
            raise PermissionError("private host details")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    report = reporter.generate_report()
    assert "读取失败" in report and "private host details" not in report
    receipt_table(report)


def test_symlinked_task_directory_is_not_followed(records, tmp_path):
    add, _ = records
    add(".agents/capsules/T1.json", capsule())
    target = tmp_path / "outside"
    target.mkdir()
    directory = tmp_path / ".agents/receipts"
    directory.mkdir()
    (directory / "T1").symlink_to(target, target_is_directory=True)
    report = reporter.generate_report()
    assert "读取失败" in report
    receipt_table(report)


def test_report_generation_does_not_modify_source_evidence(records):
    add, _ = records
    c = add(".agents/capsules/T1.json", capsule())
    r = add(".agents/receipts/T1/abc.json", receipt())
    original = [c.read_bytes(), r.read_bytes()]
    reporter.generate_report()
    assert [c.read_bytes(), r.read_bytes()] == original


@pytest.mark.parametrize("head", ["bad", "a" * 40 + "\n", "<script>" + "a" * 40])
def test_invalid_snapshot_metadata_cannot_be_published(records, monkeypatch, head):
    monkeypatch.setenv("WOM_REPORT_HEAD_SHA", head)
    with pytest.raises(ValueError):
        reporter.generate_report()
