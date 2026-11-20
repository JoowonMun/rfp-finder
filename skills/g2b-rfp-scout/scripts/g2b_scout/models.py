from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class Attachment:
    name: str
    url: str


@dataclass
class Notice:
    kind: Literal["bid", "prespec"]
    key: str
    bid_no: str
    bid_ord: str
    title: str
    agency: str
    budget_krw: int | None
    deadline: datetime | None
    posted_at: datetime | None
    category: str
    detail_url: str
    attachments: list[Attachment] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("deadline", "posted_at"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Notice":
        d = dict(d)
        for k in ("deadline", "posted_at"):
            d[k] = datetime.fromisoformat(d[k]) if d.get(k) else None
        d["attachments"] = [Attachment(**a) for a in d.get("attachments", [])]
        return cls(**d)


@dataclass
class ConvertResult:
    ok: bool
    text: str
    source_name: str | None = None
    error: str | None = None


@dataclass
class DocResult:
    ok: bool
    rfp_path: Path | None = None
    rfp_name: str | None = None
    rfp_url: str | None = None
    excerpt_path: Path | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "rfp_path": str(self.rfp_path) if self.rfp_path else None,
            "rfp_name": self.rfp_name,
            "rfp_url": self.rfp_url,
            "excerpt_path": str(self.excerpt_path) if self.excerpt_path else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocResult":
        return cls(
            ok=d["ok"],
            rfp_path=Path(d["rfp_path"]) if d.get("rfp_path") else None,
            rfp_name=d.get("rfp_name"),
            rfp_url=d.get("rfp_url"),
            excerpt_path=Path(d["excerpt_path"]) if d.get("excerpt_path") else None,
            error=d.get("error"),
        )
