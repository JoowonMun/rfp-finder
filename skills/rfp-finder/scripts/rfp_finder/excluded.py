"""적합도 0(맞지 않음) 공고의 로컬 기록. 노션 표에는 올리지 않지만 다시 분석하지 않도록 남긴다."""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import paths

KEEP_DAYS = 90  # 공고 마감 주기보다 충분히 길게


def _file():
    return paths.home() / "excluded.json"


def _load() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_keys() -> set[str]:
    return set(_load())


def add(key: str, title: str, today: date) -> None:
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    data = {k: v for k, v in _load().items() if str(v.get("date", "")) >= cutoff}
    data[key] = {"title": title, "date": today.isoformat()}
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
