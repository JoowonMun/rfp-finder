from datetime import datetime
from pathlib import Path

import pytest

from g2b_scout import paths
from g2b_scout.config import ConfigError, load_config, load_secrets
from g2b_scout.models import Attachment, Notice

MINIMAL = """
team:
  name: 테스트팀
  capabilities: AI 전환 컨설팅
filters:
  include_keywords: [AI]
notion:
  database_id: abc123
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("G2B_SCOUT_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    for k in ("DATA_GO_KR_SERVICE_KEY", "NOTION_TOKEN", "DATA_GO_KR_BID_SERVICE_KEY"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "home").mkdir()
    return tmp_path / "home"


def test_home_uses_env(home):
    assert paths.home() == home


def test_new_run_dir_created(home):
    d = paths.new_run_dir()
    assert d.is_dir() and d.parent == home / "runs"


def test_load_config_defaults(home):
    (home / "config.yaml").write_text(MINIMAL, encoding="utf-8")
    cfg = load_config()
    assert cfg.team_name == "테스트팀"
    assert cfg.include_keywords == ["AI"]
    assert cfg.exclude_keywords == []
    assert cfg.budget_min_krw is None and cfg.budget_max_krw is None
    assert cfg.min_days_to_deadline == 5
    assert cfg.include_pre_spec is True
    assert cfg.lookback_days == 30
    assert cfg.max_per_run == 15
    assert cfg.max_upload_mb == 5
    assert cfg.notion_database_id == "abc123"


def test_missing_required_raises(home):
    (home / "config.yaml").write_text(MINIMAL.replace("  capabilities: AI 전환 컨설팅\n", ""), encoding="utf-8")
    with pytest.raises(ConfigError, match="capabilities"):
        load_config()


def test_missing_config_file_raises(home):
    with pytest.raises(ConfigError, match="config.yaml"):
        load_config()


def test_load_secrets_reports_missing_key(home):
    (home / ".env").write_text("DATA_GO_KR_SERVICE_KEY=abc\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="NOTION_TOKEN"):
        load_secrets()


def test_secrets_lookup_order(home, tmp_path, monkeypatch):
    (home / ".env").write_text("DATA_GO_KR_SERVICE_KEY=from_home\nNOTION_TOKEN=n_home\n", encoding="utf-8")
    (tmp_path / ".env").write_text("DATA_GO_KR_SERVICE_KEY=from_cwd\n", encoding="utf-8")
    s = load_secrets()
    assert s.data_go_kr_service_key == "from_home"  # 홈 .env 가 현재 폴더 .env 보다 우선
    assert s.notion_token == "n_home"
    monkeypatch.setenv("NOTION_TOKEN", "n_env")
    assert load_secrets().notion_token == "n_env"


def test_notice_roundtrip():
    n = Notice(
        kind="bid", key="R26BK001-000", bid_no="R26BK001", bid_ord="000", title="AI 전환 ISP",
        agency="○○시", budget_krw=420000000, deadline=datetime(2027, 1, 15, 10, 0),
        posted_at=datetime(2026, 11, 20, 9, 0), category="일반용역", detail_url="https://x",
        attachments=[Attachment(name="제안요청서.hwp", url="https://y")],
    )
    assert Notice.from_dict(n.to_dict()) == n


def test_bid_service_key_separate_or_fallback(home, monkeypatch):
    (home / ".env").write_text("DATA_GO_KR_SERVICE_KEY=common\nNOTION_TOKEN=n\n", encoding="utf-8")
    assert load_secrets().bid_service_key == "common"
    monkeypatch.setenv("DATA_GO_KR_BID_SERVICE_KEY", "bidkey")
    s = load_secrets()
    assert s.bid_service_key == "bidkey"
    assert s.data_go_kr_service_key == "common"


def test_priority_keywords_loaded(home):
    (home / "config.yaml").write_text(MINIMAL.replace("  include_keywords: [AI]", "  include_keywords: [AI]\n  priority_keywords: [ISP, 전략]"), encoding="utf-8")
    assert load_config().priority_keywords == ["ISP", "전략"]


def test_budget_must_be_number(home):
    (home / "config.yaml").write_text(MINIMAL.replace("  include_keywords: [AI]", "  include_keywords: [AI]\n  budget_min_krw: 5천만"), encoding="utf-8")
    with pytest.raises(ConfigError, match="budget_min_krw"):
        load_config()


def test_budget_numeric_string_ok(home):
    (home / "config.yaml").write_text(MINIMAL.replace("  include_keywords: [AI]", "  include_keywords: [AI]\n  budget_max_krw: '3,000,000,000'"), encoding="utf-8")
    assert load_config().budget_max_krw == 3_000_000_000


def test_home_env_beats_cwd_env(home, tmp_path):
    (home / ".env").write_text("DATA_GO_KR_SERVICE_KEY=home\nNOTION_TOKEN=n_home\n", encoding="utf-8")
    (tmp_path / ".env").write_text("NOTION_TOKEN=other_project_token\n", encoding="utf-8")
    assert load_secrets().notion_token == "n_home"
