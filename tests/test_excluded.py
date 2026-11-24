import json
from datetime import date

from rfp_finder import excluded


def test_add_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("RFP_FINDER_HOME", str(tmp_path))
    assert excluded.load_keys() == set()
    excluded.add("B1", "AI 해커톤", date(2026, 11, 20))
    assert excluded.load_keys() == {"B1"}
    assert json.loads((tmp_path / "excluded.json").read_text(encoding="utf-8"))["B1"]["title"] == "AI 해커톤"


def test_prunes_old_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("RFP_FINDER_HOME", str(tmp_path))
    excluded.add("OLD", "a", date(2026, 8, 1))
    excluded.add("MID", "b", date(2026, 9, 1))
    assert excluded.load_keys() == {"OLD", "MID"}
    excluded.add("NEW", "c", date(2026, 11, 20))  # 추가할 때 90일 지난 항목 정리
    assert excluded.load_keys() == {"MID", "NEW"}


def test_corrupt_file_is_treated_as_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("RFP_FINDER_HOME", str(tmp_path))
    (tmp_path / "excluded.json").write_text("{broken", encoding="utf-8")
    assert excluded.load_keys() == set()
