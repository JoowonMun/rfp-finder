from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def home() -> Path:
    """사용자 설정 폴더. G2B_SCOUT_HOME으로 재정의 가능."""
    env = os.environ.get("G2B_SCOUT_HOME")
    return Path(env) if env else Path.home() / ".g2b-rfp-scout"


def new_run_dir() -> Path:
    base = home() / "runs"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = base / stamp
    n = 1
    while d.exists():
        n += 1
        d = base / f"{stamp}-{n}"
    d.mkdir(parents=True)
    return d


def logs_dir() -> Path:
    d = home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
