import json
from datetime import datetime

import pytest

import scout
from rfp_finder.g2b_api import G2BApiError
from rfp_finder.models import Attachment, Notice
from rfp_finder.notion_db import NotionError

CONFIG = """
team:
  name: 테스트팀
  capabilities: AI 전환 컨설팅
filters:
  include_keywords: [AI]
  exclude_keywords: [유지보수]
notion:
  database_id: db1
"""
NOW = datetime(2026, 11, 20, 9, 0)


def mk(key, title, kind="bid", days=20):
    from datetime import timedelta
    return Notice(kind=kind, key=key, bid_no=key, bid_ord="000", title=title, agency="기관",
                  budget_krw=None, deadline=NOW + timedelta(days=days), posted_at=NOW, category="",
                  detail_url="https://d/" + key, attachments=[Attachment("제안요청서.hwp", "https://f/" + key)])


class FakeApi:
    def __init__(self, bids, prespecs, bid_error=False):
        self.bids, self.prespecs, self.bid_error = bids, prespecs, bid_error

    def fetch_bid_notices(self, key, start, end):
        if self.bid_error:
            raise G2BApiError("조달청 API 오류 30: 등록되지 않은 서비스키")
        return self.bids

    def fetch_prespecs(self, key, start, end):
        return self.prespecs


class FakeNotion:
    def __init__(self, existing=(), fail_with_file=False):
        self.existing, self.created, self.uploads = set(existing), [], []
        self.fail_with_file = fail_with_file

    def existing_keys(self, db):
        return set(self.existing)

    def has_key(self, db, key):
        return key in self.existing

    def archive_key(self, db, key):
        self.archived = getattr(self, "archived", []) + [key]
        self.existing.discard(key)
        return 1

    def archive_older_versions(self, db, bid_no, keep_key):
        old = sorted(k for k in self.existing if k.startswith(bid_no + "-") and k != keep_key)
        self.archived_old = getattr(self, "archived_old", []) + old
        self.existing -= set(old)
        return len(old)

    def upload_file(self, path, max_mb):
        self.uploads.append(path)
        return "upl-1"

    def create_entry(self, db, notice, analysis, doc, file_upload_id, today=None):
        if self.fail_with_file and file_upload_id:
            raise NotionError("노션 API 오류 HTTP 400: file type")
        self.created.append((notice.key, file_upload_id))
        self.existing.add(notice.key)
        return {"id": "p1", "url": "https://notion.so/p1"}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    (h / "config.yaml").write_text(CONFIG, encoding="utf-8")
    (h / ".env").write_text("DATA_GO_KR_SERVICE_KEY=k\nNOTION_TOKEN=t\n", encoding="utf-8")
    monkeypatch.setenv("RFP_FINDER_HOME", str(h))
    monkeypatch.chdir(tmp_path)
    for k in ("DATA_GO_KR_SERVICE_KEY", "NOTION_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    return h


def run(capsys, argv, **kw):
    code = scout.main(argv, now=NOW, **kw)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return code, json.loads(out)


def test_candidates_writes_json(home, capsys):
    api = FakeApi([mk("B1", "AI 전략"), mk("B2", "청사 청소"), mk("B3", "AI 기존")], [mk("PS-1", "AI 사전", kind="prespec", days=3)])
    code, out = run(capsys, ["candidates"], api=api, notion=FakeNotion(existing={"B3"}))
    assert code == 0
    assert out["collected"] == 4 and out["selected"] == 2 and out["overflow"] == 0
    data = json.loads((home / "runs").glob("*/candidates.json").__next__().read_text(encoding="utf-8"))
    assert {n["key"] for n in data["selected"]} == {"B1", "PS-1"}


def test_candidates_continues_when_bid_api_fails(home, capsys):
    api = FakeApi([], [mk("PS-1", "AI 사전", kind="prespec", days=3)], bid_error=True)
    code, out = run(capsys, ["candidates"], api=api, notion=FakeNotion())
    assert code == 0 and out["selected"] == 1
    assert any("30" in w for w in out["warnings"])


def _prepare_run(home, capsys, notion):
    api = FakeApi([mk("B1", "AI 전략")], [])
    _, out = run(capsys, ["candidates"], api=api, notion=notion)
    run_dir = out["run_dir"]
    from pathlib import Path
    rd = Path(run_dir)
    f = rd / "B1" / "제안요청서.hwp"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    (rd / "docs.json").write_text(json.dumps({"B1": {"ok": True, "rfp_path": str(f), "rfp_name": "제안요청서.hwp",
                                                     "rfp_url": "https://f/B1", "excerpt_path": None, "error": None}}), encoding="utf-8")
    (rd / "analysis").mkdir()
    (rd / "analysis" / "B1.json").write_text(json.dumps({
        "bid_no": "B1", "fit": 3, "fit_reason": "r", "summary": "s",
        "detail": {"overview": "o", "requirements": [], "why_fit": [], "gaps": [], "eligibility_risks": [],
                   "evaluation": "e", "rfp_read": True}}), encoding="utf-8")
    return run_dir


def test_publish_creates_entry(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert code == 0 and out["status"] == "created" and out["page_url"] == "https://notion.so/p1"
    assert notion.created == [("B1", "upl-1")]


def test_publish_skips_duplicate(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    notion.existing.add("B1")
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert out["status"] == "skipped_duplicate" and notion.created == []


def test_publish_retries_without_file(home, capsys):
    notion = FakeNotion(fail_with_file=True)
    run_dir = _prepare_run(home, capsys, notion)
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert out["status"] == "created" and notion.created == [("B1", None)]


def test_publish_invalid_analysis_reports_error(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    from pathlib import Path
    (Path(run_dir) / "analysis" / "B1.json").write_text('{"fit": 9}', encoding="utf-8")
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert code != 0 and "fit" in out["error"] and notion.created == []


def test_summary(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    code, out = run(capsys, ["summary", "--run", run_dir])
    assert out["selected"] == 1 and out["published"] == 1 and out["by_fit"]["3"] == 1 and out["rfp_failed"] == 0


def test_doctor_reports_missing_config(home, capsys):
    (home / "config.yaml").unlink()
    code, out = run(capsys, ["doctor"], notion=FakeNotion())
    assert out["ok"] is False and any("config.yaml" in p for p in out["problems"])
    assert out["needs"] == ["config"] or "config" in out["needs"]


def test_setup_notion_writes_database_id(home, capsys):
    class N(FakeNotion):
        def create_database(self, parent, title="나라장터 추천 공고"):
            return "new-db-id"
    code, out = run(capsys, ["setup-notion", "--parent-page", "1f2e3d4c5b6a79881f2e3d4c5b6a7988"], notion=N())
    assert out["database_id"] == "new-db-id"
    assert "database_id: new-db-id" in (home / "config.yaml").read_text(encoding="utf-8")


def test_fetch_fills_missing_bid_attachments(home, capsys, monkeypatch):
    no_att = mk("B9", "AI 전략")
    no_att.attachments = []
    api = FakeApi([no_att], [])
    api.fetch_bid_attachments = lambda key, no, ord_: [Attachment("제안요청서.hwpx", "https://f/B9")]
    _, out = run(capsys, ["candidates"], api=api, notion=FakeNotion())
    seen = {}

    def fake_fetch(notice, out_dir, session=None):
        from rfp_finder.models import DocResult
        seen[notice.key] = [a.url for a in notice.attachments]
        return DocResult(ok=False, error="test")
    monkeypatch.setattr(scout, "fetch_documents", fake_fetch)
    run(capsys, ["fetch", "--run", out["run_dir"]], api=api)
    assert seen == {"B9": ["https://f/B9"]}
    from pathlib import Path
    saved = json.loads((Path(out["run_dir"]) / "candidates.json").read_text(encoding="utf-8"))
    assert saved["selected"][0]["attachments"][0]["url"] == "https://f/B9"


def _set_fit(run_dir, fit):
    from pathlib import Path
    p = Path(run_dir) / "analysis" / "B1.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["fit"] = fit
    p.write_text(json.dumps(d), encoding="utf-8")


def test_publish_fit0_is_recorded_locally_not_in_notion(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    _set_fit(run_dir, 0)
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert code == 0 and out["status"] == "excluded"
    assert notion.created == [] and notion.uploads == []
    assert "B1" in json.loads((home / "excluded.json").read_text(encoding="utf-8"))
    code, out = run(capsys, ["summary", "--run", run_dir])
    assert out["by_fit"]["0"] == 1 and out["published"] == 0 and out["excluded"] == 1


def test_publish_fit1_goes_to_notion(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    _set_fit(run_dir, 1)
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert code == 0 and out["status"] == "created" and len(notion.created) == 1
    code, out = run(capsys, ["summary", "--run", run_dir])
    assert out["by_fit"]["1"] == 1 and out["published"] == 1 and out["excluded"] == 0


def test_candidates_skips_locally_excluded(home, capsys):
    (home / "excluded.json").write_text(json.dumps({"B1": {"title": "x", "date": "2026-11-19"}}), encoding="utf-8")
    api = FakeApi([mk("B1", "AI 전략"), mk("B2", "AI 기획")], [])
    code, out = run(capsys, ["candidates"], api=api, notion=FakeNotion())
    assert out["selected"] == 1


def test_publish_malformed_json_is_analysis_error(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    from pathlib import Path
    (Path(run_dir) / "analysis" / "B1.json").write_text('{"fit": 3,}', encoding="utf-8")
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert code == 1 and out["error"].startswith("분석 JSON 오류")


def test_fetch_one_notice_crash_does_not_abort_run(home, capsys, monkeypatch):
    api = FakeApi([mk("B1", "AI 전략"), mk("B2", "AI 기획")], [])
    _, out = run(capsys, ["candidates"], api=api, notion=FakeNotion())
    from rfp_finder.models import DocResult

    def flaky(notice, out_dir, session=None):
        if notice.key == "B1":
            raise OSError("disk full")
        return DocResult(ok=False, error="x")
    monkeypatch.setattr(scout, "fetch_documents", flaky)
    code, res = run(capsys, ["fetch", "--run", out["run_dir"]], api=api)
    assert code == 0 and res["failed"] == 2
    from pathlib import Path
    docs = json.loads((Path(out["run_dir"]) / "docs.json").read_text(encoding="utf-8"))
    assert "disk full" in docs["B1"]["error"]


def test_unexpected_exception_still_emits_json(home, capsys):
    class Boom(FakeNotion):
        def existing_keys(self, db):
            raise RuntimeError("unexpected")
    code, out = run(capsys, ["candidates"], api=FakeApi([], []), notion=Boom())
    assert code == 1 and out["ok"] is False and "unexpected" in out["error"]


def test_candidates_fails_when_all_sources_fail(home, capsys):
    class Down(FakeApi):
        def fetch_prespecs(self, key, start, end):
            raise G2BApiError("사전규격 다운")
    code, out = run(capsys, ["candidates"], api=Down([], [], bid_error=True), notion=FakeNotion())
    assert code == 1 and out["ok"] is False and len(out["warnings"]) == 2


def test_publish_replace_rebuilds_existing_page(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    notion.existing.add("B1")
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1", "--replace"], notion=notion)
    assert out["status"] == "created" and notion.archived == ["B1"] and notion.created == [("B1", "upl-1")]


def test_publish_replace_fit0_archives_and_excludes(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    notion.existing.add("B1")
    _set_fit(run_dir, 0)
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1", "--replace"], notion=notion)
    assert out["status"] == "excluded" and notion.archived == ["B1"] and notion.created == []


def test_publish_archives_older_versions_of_same_bid(home, capsys):
    notion = FakeNotion()
    run_dir = _prepare_run(home, capsys, notion)
    notion.existing.add("B1-000")  # 같은 입찰번호의 이전 차수
    code, out = run(capsys, ["publish", "--run", run_dir, "--key", "B1"], notion=notion)
    assert out["status"] == "created"
    assert notion.archived_old == ["B1-000"] and "B1-000" not in notion.existing
