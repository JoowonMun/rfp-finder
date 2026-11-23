from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values

from . import paths


class ConfigError(Exception):
    pass


@dataclass
class Config:
    team_name: str
    capabilities: str
    notion_database_id: str
    include_keywords: list[str]
    past_projects: str = ""
    exclude_keywords: list[str] = field(default_factory=list)
    priority_keywords: list[str] = field(default_factory=list)
    budget_min_krw: int | None = None
    budget_max_krw: int | None = None
    min_days_to_deadline: int = 5
    include_pre_spec: bool = True
    lookback_days: int = 30
    max_per_run: int = 15
    max_upload_mb: int = 5


@dataclass
class Secrets:
    data_go_kr_service_key: str
    notion_token: str
    bid_service_key: str = ""  # 입찰공고 서비스 전용 키. 비어 있으면 공용 키 사용

    def __post_init__(self):
        if not self.bid_service_key:
            self.bid_service_key = self.data_go_kr_service_key


def config_path() -> Path:
    return paths.home() / "config.yaml"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise ConfigError(f"설정 파일이 없습니다: {path} (config.yaml)")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    team = raw.get("team") or {}
    filters = raw.get("filters") or {}
    collect = raw.get("collect") or {}
    notion = raw.get("notion") or {}

    missing = []
    if not team.get("name"):
        missing.append("team.name")
    if not team.get("capabilities"):
        missing.append("team.capabilities")
    if not filters.get("include_keywords"):
        missing.append("filters.include_keywords")
    if missing:
        raise ConfigError("config.yaml 필수 항목 누락: " + ", ".join(missing))

    return Config(
        team_name=str(team["name"]),
        capabilities=str(team["capabilities"]).strip(),
        past_projects=str(team.get("past_projects") or "").strip(),
        notion_database_id=str(notion.get("database_id") or ""),
        include_keywords=[str(k) for k in filters["include_keywords"]],
        exclude_keywords=[str(k) for k in filters.get("exclude_keywords") or []],
        priority_keywords=[str(k) for k in filters.get("priority_keywords") or []],
        budget_min_krw=filters.get("budget_min_krw"),
        budget_max_krw=filters.get("budget_max_krw"),
        min_days_to_deadline=int(filters.get("min_days_to_deadline", 5)),
        include_pre_spec=bool(filters.get("include_pre_spec", True)),
        lookback_days=int(collect.get("lookback_days", 30)),
        max_per_run=int(collect.get("max_per_run", 15)),
        max_upload_mb=int(notion.get("max_upload_mb", 5)),
    )


_SECRET_NAMES = ("DATA_GO_KR_SERVICE_KEY", "NOTION_TOKEN")
_OPTIONAL_NAMES = ("DATA_GO_KR_BID_SERVICE_KEY",)


def load_secrets() -> Secrets:
    """환경변수 → 현재 폴더 .env → 홈 .env 순으로 먼저 찾은 값."""
    sources = [
        dict(os.environ),
        dotenv_values(Path.cwd() / ".env"),
        dotenv_values(paths.home() / ".env"),
    ]
    found: dict[str, str] = {}
    for name in _SECRET_NAMES + _OPTIONAL_NAMES:
        for src in sources:
            val = (src.get(name) or "").strip()
            if val:
                found[name] = val
                break
    missing = [n for n in _SECRET_NAMES if n not in found]
    if missing:
        raise ConfigError(".env에 값이 없습니다: " + ", ".join(missing))
    return Secrets(found["DATA_GO_KR_SERVICE_KEY"], found["NOTION_TOKEN"], found.get("DATA_GO_KR_BID_SERVICE_KEY", ""))
