"""g2b-rfp-scout CLI. 모든 하위 명령은 결과를 stdout 마지막 줄에 JSON 한 줄로 출력한다.

  python scout.py doctor
  python scout.py setup-notion --parent-page <노션 페이지 URL 또는 ID>
  python scout.py candidates
  python scout.py fetch   --run <run_dir>
  python scout.py publish --run <run_dir> --key <공고키>
  python scout.py summary --run <run_dir>
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from g2b_scout import g2b_api, paths  # noqa: E402
from g2b_scout.analysis import AnalysisError, validate_analysis  # noqa: E402
from g2b_scout.config import ConfigError, config_path, load_config, load_secrets  # noqa: E402
from g2b_scout.fetch import fetch_documents, safe_filename  # noqa: E402
from g2b_scout.models import DocResult, Notice  # noqa: E402
from g2b_scout.notion_db import NotionClient, NotionError  # noqa: E402
from g2b_scout.prefilter import select_candidates  # noqa: E402


class CliError(Exception):
    pass


# ---------- 공통 ----------

def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, default=str))


def _log(msg: str) -> None:
    try:
        f = paths.logs_dir() / f"{datetime.now():%Y%m%d}.log"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


def _collector() -> str:
    return os.environ.get("G2B_SCOUT_COLLECTOR") or getpass.getuser()


def _read_json(p: Path, default=None):
    if not p.exists():
        if default is not None:
            return default
        raise CliError(f"파일 없음: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, data) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _notion(ctx, secrets):
    return ctx["notion"] or NotionClient(secrets.notion_token)


def _require_db(cfg) -> str:
    if not cfg.notion_database_id:
        raise CliError("config.yaml 에 notion.database_id 가 없습니다. setup-notion 을 먼저 실행하세요.")
    return cfg.notion_database_id


# ---------- 명령 ----------

def cmd_doctor(args, ctx) -> dict:
    problems, needs = [], []
    cfg = secrets = None
    try:
        cfg = load_config()
    except ConfigError as e:
        problems.append(str(e))
        needs.append("config")
    try:
        secrets = load_secrets()
    except ConfigError as e:
        problems.append(str(e))
        needs.append("secrets")
    if cfg and not cfg.notion_database_id:
        problems.append("notion.database_id 없음")
        needs.append("notion_db")
    if cfg and secrets and cfg.notion_database_id:
        try:
            n = _notion(ctx, secrets)
            if hasattr(n, "get_database"):
                n.get_database(cfg.notion_database_id)
        except NotionError as e:
            problems.append(f"노션 DB 접근 실패: {e} (통합을 DB가 있는 페이지에 연결했는지 확인)")
            needs.append("notion_access")
    return {"ok": not problems, "problems": problems, "needs": needs, "home": str(paths.home())}


def cmd_setup_notion(args, ctx) -> dict:
    load_config()  # config 먼저 있어야 함
    secrets = load_secrets()
    db_id = _notion(ctx, secrets).create_database(args.parent_page)
    p = config_path()
    text = p.read_text(encoding="utf-8")
    if re.search(r"^\s*database_id\s*:.*$", text, re.M):
        text = re.sub(r"^(\s*)database_id\s*:.*$", lambda m: f"{m.group(1)}database_id: {db_id}", text, count=1, flags=re.M)
    elif re.search(r"^notion\s*:\s*$", text, re.M):
        text = re.sub(r"^notion\s*:\s*$", f"notion:\n  database_id: {db_id}", text, count=1, flags=re.M)
    else:
        text = text.rstrip() + f"\nnotion:\n  database_id: {db_id}\n"
    p.write_text(text, encoding="utf-8")
    _log(f"setup-notion: database {db_id}")
    return {"database_id": db_id}


def cmd_candidates(args, ctx) -> dict:
    cfg = load_config()
    secrets = load_secrets()
    db = _require_db(cfg)
    api = ctx["api"] or g2b_api
    now = ctx["now"]
    start, end = (now - timedelta(days=cfg.lookback_days)).date(), now.date()

    notices: list[Notice] = []
    warnings: list[str] = []
    try:
        notices += api.fetch_bid_notices(secrets.bid_service_key, start, end)
    except g2b_api.G2BApiError as e:
        warnings.append(f"입찰공고 수집 실패: {e}")
    if cfg.include_pre_spec:
        try:
            notices += api.fetch_prespecs(secrets.data_go_kr_service_key, start, end)
        except g2b_api.G2BApiError as e:
            warnings.append(f"사전규격 수집 실패: {e}")

    existing = _notion(ctx, secrets).existing_keys(db)
    selected, overflow = select_candidates(notices, existing, cfg, now)
    new_count = len({n.key for n in notices} - existing)

    run_dir = paths.new_run_dir()
    _write_json(run_dir / "candidates.json", {
        "selected": [n.to_dict() for n in selected],
        "overflow": [n.to_dict() for n in overflow],
        "warnings": warnings,
    })
    result = {
        "run_dir": str(run_dir), "collected": len(notices), "new": new_count,
        "selected": len(selected), "overflow": len(overflow), "warnings": warnings,
    }
    _log(f"candidates: {result}")
    return result


def _selected(run_dir: Path) -> list[Notice]:
    return [Notice.from_dict(d) for d in _read_json(run_dir / "candidates.json")["selected"]]


def cmd_fetch(args, ctx) -> dict:
    run_dir = Path(args.run)
    api = ctx["api"] or g2b_api
    selected = _selected(run_dir)
    # 목록 응답에 첨부 URL이 없던 입찰공고는 첨부파일정보 오퍼레이션으로 보충
    missing = [n for n in selected if n.kind == "bid" and not n.attachments]
    if missing:
        secrets = load_secrets()
        for n in missing:
            try:
                n.attachments = api.fetch_bid_attachments(secrets.bid_service_key, n.bid_no, n.bid_ord)
            except g2b_api.G2BApiError as e:
                _log(f"fetch {n.key}: 첨부정보 조회 실패 {e}")
        cands = _read_json(run_dir / "candidates.json")
        cands["selected"] = [n.to_dict() for n in selected]
        _write_json(run_dir / "candidates.json", cands)
    docs = {}
    for n in selected:
        docs[n.key] = fetch_documents(n, run_dir / "docs").to_dict()
        _log(f"fetch {n.key}: ok={docs[n.key]['ok']} {docs[n.key].get('error') or ''}")
    _write_json(run_dir / "docs.json", docs)
    ok = sum(1 for d in docs.values() if d["ok"])
    return {"ok": ok, "failed": len(docs) - ok, "docs": {k: {"ok": d["ok"], "excerpt_path": d["excerpt_path"]} for k, d in docs.items()}}


def cmd_publish(args, ctx) -> dict:
    run_dir = Path(args.run)
    cfg = load_config()
    secrets = load_secrets()
    db = _require_db(cfg)
    notice = next((n for n in _selected(run_dir) if n.key == args.key), None)
    if notice is None:
        raise CliError(f"candidates.json 에 없는 키: {args.key}")
    try:
        analysis = validate_analysis(_read_json(run_dir / "analysis" / f"{safe_filename(args.key)}.json"))
    except AnalysisError as e:
        raise CliError(f"분석 JSON 오류: {e}") from None
    doc_raw = _read_json(run_dir / "docs.json", default={}).get(args.key)
    doc = DocResult.from_dict(doc_raw) if doc_raw else DocResult(ok=False, error="문서 미처리")

    notion = _notion(ctx, secrets)
    if notion.has_key(db, notice.key):
        return {"key": notice.key, "status": "skipped_duplicate", "page_url": None}

    upload_id = None
    if doc.rfp_path and Path(doc.rfp_path).exists():
        upload_id = notion.upload_file(Path(doc.rfp_path), cfg.max_upload_mb)
    try:
        page = notion.create_entry(db, notice, analysis, doc, upload_id, _collector(), ctx["now"].date())
    except NotionError:
        if not upload_id:
            raise
        _log(f"publish {notice.key}: 파일 첨부 실패 → 링크로 재시도")
        page = notion.create_entry(db, notice, analysis, doc, None, _collector(), ctx["now"].date())

    published = _read_json(run_dir / "published.json", default={})
    published[notice.key] = {"fit": analysis["fit"], "rfp_ok": doc.ok, "url": page.get("url"), "title": notice.title,
                             "deadline": notice.deadline.isoformat() if notice.deadline else None}
    _write_json(run_dir / "published.json", published)
    _log(f"publish {notice.key}: fit={analysis['fit']} file={'upload' if upload_id else 'link'}")
    return {"key": notice.key, "status": "created", "page_url": page.get("url")}


def cmd_summary(args, ctx) -> dict:
    run_dir = Path(args.run)
    cands = _read_json(run_dir / "candidates.json")
    published = _read_json(run_dir / "published.json", default={})
    by_fit = {"3": 0, "2": 0, "1": 0}
    for p in published.values():
        by_fit[str(p["fit"])] += 1
    top = [{"title": p["title"], "deadline": p["deadline"], "url": p["url"]} for p in published.values() if p["fit"] == 3]
    return {
        "selected": len(cands["selected"]), "published": len(published), "by_fit": by_fit,
        "rfp_failed": sum(1 for p in published.values() if not p["rfp_ok"]),
        "overflow": len(cands["overflow"]), "warnings": cands.get("warnings", []), "top": top,
    }


# ---------- 진입점 ----------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scout.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    s = sub.add_parser("setup-notion")
    s.add_argument("--parent-page", required=True)
    sub.add_parser("candidates")
    for name in ("fetch", "summary"):
        sub.add_parser(name).add_argument("--run", required=True)
    s = sub.add_parser("publish")
    s.add_argument("--run", required=True)
    s.add_argument("--key", required=True)
    return p


COMMANDS = {
    "doctor": cmd_doctor, "setup-notion": cmd_setup_notion, "candidates": cmd_candidates,
    "fetch": cmd_fetch, "publish": cmd_publish, "summary": cmd_summary,
}


def main(argv=None, *, api=None, notion=None, now: datetime | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    ctx = {"api": api, "notion": notion, "now": now or datetime.now()}
    try:
        result = COMMANDS[args.cmd](args, ctx)
    except (CliError, ConfigError, NotionError, g2b_api.G2BApiError) as e:
        _log(f"{args.cmd} 오류: {e}")
        _emit({"ok": False, "error": str(e)})
        return 1
    _emit(result)
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
