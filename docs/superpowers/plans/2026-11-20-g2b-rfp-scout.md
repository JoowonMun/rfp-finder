# g2b-rfp-scout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 나라장터 용역 공고·사전규격을 수집하고 제안요청서 본문을 읽어 팀 적합도를 매긴 뒤 팀 노션 DB에 쌓는 Claude Code 스킬(플러그인)을 만든다.

**Architecture:** 결정적인 작업(API 수집, 중복 확인, 키워드 필터, 첨부 다운로드·변환, 노션 업로드)은 Python CLI `scout.py`의 하위 명령으로 만들고, 판단(적합도·요약·상세 분석)은 SKILL.md 지침에 따라 Claude가 한다. 둘 사이는 실행 폴더(`%USERPROFILE%\.g2b-rfp-scout\runs\<timestamp>\`)의 JSON/텍스트 파일로 주고받는다. 처리 기록의 유일한 출처는 노션 DB의 `공고번호` 속성.

**Tech Stack:** Python 3.10+, requests, PyYAML, python-dotenv, olefile, pdfplumber, pytest. Notion REST API, 공공데이터포털 조달청 OpenAPI. Claude Code plugin/marketplace 형식.

**Spec:** `docs/superpowers/specs/2026-11-20-g2b-rfp-scout-design.md`

## Global Constraints

- Python 3.10+, Windows 11 우선 (경로는 `pathlib`, 콘솔/파일 인코딩은 UTF-8 명시).
- 데이터 출처는 공공데이터포털 OpenAPI만. 나라장터 화면 스크래핑 금지.
- 비밀(`DATA_GO_KR_SERVICE_KEY`, `NOTION_TOKEN`)은 `%USERPROFILE%\.g2b-rfp-scout\.env`에만. 저장소·로그·노션 어디에도 출력 금지.
- 사용자 설정은 `%USERPROFILE%\.g2b-rfp-scout\config.yaml` (환경변수 `G2B_SCOUT_HOME`으로 홈 폴더 재정의 가능 — 테스트용).
- 공개 저장소: 팀 고유 정보(실제 config, 팀 역량 서술, DB ID) 커밋 금지. `config.example.yaml`만.
- 적합도 1~3 → 노션 `★`, `★★`, `★★★`. fit==1이면 상태 `자동제외`, 아니면 `검토전`.
- 노션 파일 업로드 상한 `notion.max_upload_mb` 기본 5. 초과·실패 시 외부 링크로 대체. 분할 업로드 없음.
- 실행당 분석 상한 `collect.max_per_run` 기본 15, `collect.lookback_days` 기본 3, `filters.min_days_to_deadline` 기본 5 (본공고만).
- 중복 키: 본공고 `"{bid_no}-{bid_ord}"`, 사전규격 `"PS-{reg_no}"`.
- 노션 DB 속성 이름은 스펙 6.5 표 그대로(한글): 공고명, 구분, 발주기관, 예산, 마감일, 적합도, 한줄 요약, 제안요청서, 원문 링크, 상태, RFP 분석, 공고번호, 수집일, 수집자.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **API 결과 0건 또는 1건** — 조달청 API는 0건이면 `items`가 빈 문자열, 1건이면 리스트 대신 dict로 줄 수 있다. 크래시 없이 0건/1건으로 처리해야 한다. → Task 3 `test_parse_items_handles_empty_and_single`.
2. **예산 미기재·문자열·0** — `""`, `"1,000,000"`, `"0"`, 누락. 미기재는 `None`으로 두고 예산 필터를 통과시킨다(스펙). → Task 3 `test_parse_budget_variants`, Task 4 `test_budget_none_passes`.
3. **텍스트 없는 PDF(스캔본)·손상된 HWP·모르는 확장자** — 예외로 실행이 멈추면 안 되고 `ConvertResult(ok=False)`로 돌아와 노션에 `RFP 분석: 실패`로 표시돼야 한다. → Task 5 `test_convert_failures_do_not_raise`.
4. **노션 DB에 기존 행이 100개 넘음** — 중복 조회가 첫 페이지만 읽으면 중복이 생긴다. 페이지네이션 필수. → Task 7 `test_existing_keys_paginates`.
5. **한글·퍼센트 인코딩 첨부 파일명** — Windows에서 쓸 수 없는 문자, 매우 긴 이름. 저장 파일명은 정리하고 원래 이름은 노션 표시용으로 유지. → Task 6 `test_safe_filename`.

---

## File Structure

```
.claude-plugin/
  marketplace.json              # 저장소 = 마켓플레이스, 플러그인 소스 "./"
  plugin.json
skills/g2b-rfp-scout/
  SKILL.md                      # 실행 절차 (Task 9)
  references/analysis-guide.md  # 적합도 기준, 분석 JSON 스키마 (Task 9)
  references/setup-guide.md     # 키·토큰 발급, 첫 설정 (Task 9)
  config.example.yaml           # (Task 2)
  scripts/
    scout.py                    # CLI 진입점 (Task 8)
    g2b_scout/
      __init__.py
      paths.py                  # 홈/실행 폴더 경로 (Task 2)
      config.py                 # Config 로드·검증 (Task 2)
      models.py                 # Notice, Attachment, ConvertResult, Analysis (Task 2)
      g2b_api.py                # 조달청 API 호출·파싱 (Task 3)
      prefilter.py              # 키워드·예산·마감 필터, 우선순위, 상한 (Task 4)
      convert/__init__.py       # convert(path) 디스패치, pick_rfp (Task 5)
      convert/hwpx.py
      convert/hwp5.py
      convert/pdf.py
      excerpt.py                # RFP 발췌 (Task 5)
      fetch.py                  # 첨부 다운로드 (Task 6)
      notion_db.py              # 노션 클라이언트 + 속성/블록 빌더 (Task 7)
      analysis.py               # 분석 JSON 검증 (Task 8)
tools/spike_api.py              # API 명세 확인용 (Task 1)
scheduler/register-task.ps1     # 작업 스케줄러 등록 (Task 10)
tests/                          # pytest, fixtures/
pyproject.toml                  # pytest 설정 (pythonpath = skills/g2b-rfp-scout/scripts)
requirements.txt
README.md  LICENSE
```

---

### Task 1: 스캐폴드 + 조달청 API 스파이크 (게이트)

스펙 3·6.3: 차세대 전환 후 엔드포인트·필드명을 실제 호출로 확인한다. **첨부(제안요청서) 다운로드 URL이 응답에 없으면 여기서 멈추고 사용자에게 보고한다.**

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `tools/spike_api.py`, `tests/fixtures/api/` (응답 샘플), `docs/api-notes.md`

**Prerequisite (사용자):** 공공데이터포털에서 "조달청_나라장터 입찰공고정보서비스", "조달청_나라장터 사전규격정보서비스" 활용신청 후 서비스키를 `%USERPROFILE%\.g2b-rfp-scout\.env`의 `DATA_GO_KR_SERVICE_KEY`에 저장. 키가 없으면 사용자에게 요청하고 대기.

- [ ] **Step 1:** `requirements.txt`(requests, PyYAML, python-dotenv, olefile, pdfplumber; dev: pytest), `pyproject.toml`(`[tool.pytest.ini_options] pythonpath = ["skills/g2b-rfp-scout/scripts"]`, `testpaths = ["tests"]`) 작성, `python -m venv .venv` 후 설치.
- [ ] **Step 2:** `tools/spike_api.py` 작성 — `.env`에서 키를 읽어 아래 후보 엔드포인트를 차례로 `type=json`, 최근 3일, `numOfRows=10`으로 호출하고 첫 성공 응답을 `tests/fixtures/api/<name>.json`에 저장. 후보(data.go.kr 상세 페이지에서 최신 경로 우선 확인):
  - 입찰공고(용역): `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc`, 구 경로 `.../1230000/BidPublicInfoService05/getBidPblancListInfoServcPPSSrch`
  - 사전규격(용역): `https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc`, 구 경로 `.../1230000/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc`
- [ ] **Step 3:** 실행: `.venv\Scripts\python tools\spike_api.py` → 두 fixture 파일 생성, 응답 `resultCode == "00"`.
- [ ] **Step 4:** `docs/api-notes.md`에 확정 엔드포인트, 요청 파라미터(날짜 형식 포함), 그리고 아래 필드의 실제 키 이름을 표로 기록: 공고번호, 차수, 공고명, 수요/공고기관, 예산(배정·추정가격), 입찰 마감일시, 공고 상세 URL, 첨부파일명·URL(1~10), 업무구분/분류, 공고일시, 사전규격 등록번호·의견마감일·규격서 파일. 필드 하나라도 없으면 "없음"으로 적는다.
- [ ] **Step 5: 게이트** — fixture의 첨부 URL 하나를 브라우저 없이 `requests.get`으로 받아 파일이 내려오는지(HTML 로그인 페이지가 아닌지, Content-Type/시그니처 확인) 검증해 결과를 api-notes에 기록. **실패하면 Task 2 이후로 진행하지 말고 사용자에게 api-notes를 보여주고 결정을 받는다.**
- [ ] **Step 6:** 커밋 (`.env`가 스테이징되지 않았는지 `git status`로 확인).
```bash
git add pyproject.toml requirements.txt tools/ tests/fixtures/api docs/api-notes.md
git commit -m "chore: scaffold and record g2b API spike results"
```

---

### Task 2: 경로·설정·모델

**Files:**
- Create: `scripts/g2b_scout/{__init__,paths,config,models}.py`, `skills/g2b-rfp-scout/config.example.yaml`
- Test: `tests/test_config.py`

(이하 `scripts/` = `skills/g2b-rfp-scout/scripts/`)

**Interfaces:**
- Produces:
  - `paths.home() -> Path` (`G2B_SCOUT_HOME` 또는 `~/.g2b-rfp-scout`), `paths.new_run_dir() -> Path` (`home()/runs/YYYYMMDD-HHMMSS`, 생성)
  - `config.load_config(path: Path | None = None) -> Config`; `config.load_secrets() -> Secrets` (없는 키는 `ConfigError`로 어떤 키가 없는지 명시)
  - `Config` 필드: `team_name: str, capabilities: str, past_projects: str, include_keywords: list[str], exclude_keywords: list[str], budget_min_krw: int|None, budget_max_krw: int|None, min_days_to_deadline: int=5, include_pre_spec: bool=True, lookback_days: int=3, max_per_run: int=15, notion_database_id: str, max_upload_mb: int=5`
  - `models.Attachment(name: str, url: str)`
  - `models.Notice(kind: Literal["bid","prespec"], key: str, bid_no: str, bid_ord: str, title: str, agency: str, budget_krw: int|None, deadline: datetime|None, posted_at: datetime|None, category: str, detail_url: str, attachments: list[Attachment])` + `to_dict()/from_dict()` (JSON 왕복)
  - `models.ConvertResult(ok: bool, text: str, source_name: str|None, error: str|None)`

- [ ] **Step 1: 실패하는 테스트 작성** — `test_load_config_defaults` (filters·collect 생략한 최소 yaml → 기본값 5/True/3/15/5), `test_missing_required_raises` (`team.capabilities` 없음 → `ConfigError` 메시지에 `capabilities` 포함), `test_load_secrets_reports_missing_key`, `test_notice_roundtrip` (`Notice.from_dict(n.to_dict()) == n`, datetime 포함).
- [ ] **Step 2:** `pytest tests/test_config.py -v` → FAIL (모듈 없음).
- [ ] **Step 3:** 구현. `config.example.yaml`은 스펙 6.2 예시를 일반화(팀명·역량은 "여기에 팀 소개" 같은 자리표시자, 키워드 예시는 유지).
- [ ] **Step 4:** `pytest tests/test_config.py -v` → PASS.
- [ ] **Step 5:** 커밋 `feat: config, paths, models`.

---

### Task 3: 조달청 API 클라이언트

필드 키는 Task 1의 `docs/api-notes.md`를 따른다.

**Files:**
- Create: `scripts/g2b_scout/g2b_api.py`
- Test: `tests/test_g2b_api.py` (fixtures: `tests/fixtures/api/*.json` + 직접 만든 0건/1건 응답)

**Interfaces:**
- Consumes: `Notice`, `Attachment`
- Produces:
  - `parse_items(payload: dict) -> list[dict]` — `response.body.items`를 정규화(빈 문자열→[], dict→[dict], `{"item": ...}` 래핑도 처리)
  - `parse_bid(item: dict) -> Notice`, `parse_prespec(item: dict) -> Notice`
  - `parse_budget(value) -> int | None`
  - `fetch_bid_notices(service_key: str, start: date, end: date, session=requests) -> list[Notice]` — 전 페이지 순회(`totalCount` 기준), 용역만
  - `fetch_prespecs(service_key: str, start: date, end: date, session=requests) -> list[Notice]`
  - `G2BApiError` — `resultCode != "00"` 시 코드·메시지 포함(서비스키 미포함)

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_parse_bid_from_fixture` — fixture 첫 항목 → `kind=="bid"`, `key==f"{bid_no}-{bid_ord}"`, 첨부 1개 이상, `deadline` tz 없는 datetime
  - `test_parse_prespec_from_fixture` — `key.startswith("PS-")`, `deadline`=의견마감일
  - `test_parse_items_handles_empty_and_single` — `items=""` → `[]`; `items={"item": {...}}` → 길이 1
  - `test_parse_budget_variants` — `""`→None, `None`→None, `"0"`→None, `"1,000,000"`→1000000, `"250000000"`→250000000
  - `test_fetch_paginates` — 가짜 session이 totalCount=25, numOfRows=10이면 3번 호출되고 25건 반환
  - `test_api_error_hides_key` — resultCode "30" → `G2BApiError`, 메시지에 서비스키 문자열 없음
- [ ] **Step 2:** `pytest tests/test_g2b_api.py -v` → FAIL.
- [ ] **Step 3:** 구현. 빈 첨부 URL 필드는 건너뜀. 날짜 파싱은 api-notes의 형식.
- [ ] **Step 4:** PASS 확인.
- [ ] **Step 5:** 커밋 `feat: g2b API client`.

---

### Task 4: prefilter, 우선순위, 상한

스펙 6.8 규칙 그대로.

**Files:**
- Create: `scripts/g2b_scout/prefilter.py`
- Test: `tests/test_prefilter.py`

**Interfaces:**
- Consumes: `Notice`, `Config`
- Produces:
  - `keyword_hits(notice: Notice, keywords: list[str]) -> int` — 공고명+category 대상, 대소문자 무시
  - `passes(notice: Notice, cfg: Config, now: datetime) -> bool`
  - `select_candidates(notices: list[Notice], existing_keys: set[str], cfg: Config, now: datetime) -> tuple[list[Notice], list[Notice]]` — (이번에 처리할 것, 상한 초과분). 순서: 중복 제거 → `passes` → 우선순위 정렬(포함 키워드 매칭 수 내림차순, 마감 오름차순, 마감 None은 뒤) → `max_per_run`에서 자름

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_requires_include_keyword` — "청사 시설 유지관리 용역" 탈락
  - `test_exclude_only_drops` — "전산장비 유지보수"(포함 없음) 탈락
  - `test_exclude_with_include_passes` — "AI 플랫폼 구축 및 유지보수" 통과
  - `test_budget_range` / `test_budget_none_passes`
  - `test_bid_deadline_min_days` — 마감 4일 후 탈락, 5일 후 통과
  - `test_prespec_ignores_min_days_but_drops_expired` — 사전규격 마감 2일 후 통과, 어제 마감 탈락
  - `test_prespec_excluded_when_disabled` — `include_pre_spec=False`면 사전규격 전부 탈락
  - `test_dedupe_and_cap_order` — 기존 키 제외, 17건 통과 시 15/2 분할, 매칭 많은 순→마감 빠른 순
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현.
- [ ] **Step 4:** PASS 확인.
- [ ] **Step 5:** 커밋 `feat: prefilter and candidate selection`.

---

### Task 5: 문서 변환 + RFP 선택 + 발췌

스펙 6.3. **HWP5는 스펙의 pyhwp 대신 olefile로 직접 파싱한다** — pyhwp는 Python 3 지원이 불안정하고, 텍스트 추출만 필요하면 `BodyText/Section*` 스트림(zlib raw deflate, `FileHeader` 압축 플래그 확인)에서 HWPTAG_PARA_TEXT(tag id 67) 레코드를 읽는 것으로 충분하다(표 셀 텍스트도 문단이라 포함됨). 배포 시 설치도 가벼움.

**Files:**
- Create: `scripts/g2b_scout/convert/{__init__,hwpx,hwp5,pdf}.py`, `scripts/g2b_scout/excerpt.py`
- Test: `tests/test_convert.py`, `tests/test_excerpt.py`, fixtures `tests/fixtures/docs/` (Task 1에서 받은 실제 HWP/PDF 중 작은 것 1개씩; 공공 문서이므로 커밋 가능, 각 1MB 이하로 선택)

**Interfaces:**
- Consumes: `ConvertResult`, `Attachment`
- Produces:
  - `convert.convert(path: Path) -> ConvertResult` — 확장자/시그니처로 분기(`.hwpx`→hwpx, `.hwp`→hwp5, `.pdf`→pdf, `.zip`→내부 파일 각각 변환해 `pick_rfp` 순서로 이어붙임). **예외를 밖으로 던지지 않는다.** 추출 텍스트가 200자 미만이면 `ok=False, error="no text"`.
  - `convert.pick_rfp(names: list[str]) -> list[str]` — 우선순위: 이름에 `제안요청서` > `과업지시서|과업내용서` > `규격서|사양서` > 기타; 같은 등급은 원래 순서
  - `hwpx.extract(path) -> str`, `hwp5.extract(path) -> str`, `pdf.extract(path) -> str`
  - `excerpt.make_excerpt(text: str, max_chars: int = 60000) -> str` — 넘지 않으면 원문. 넘으면 문단을 나눠 제목 줄이 `과업|요구사항|평가|자격|제안|사업 개요|추진`에 매칭되는 섹션을 앞에서부터 우선 채우고, 남는 분량은 문서 앞부분으로 채운 뒤 끝에 `[... 일부 생략 ...]` 표시

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_hwpx_extract` — 테스트 안에서 `Contents/section0.xml`에 `<hp:t>사업명: AI 전환 컨설팅</hp:t>`을 넣은 zip을 만들어 `.hwpx`로 저장 → 텍스트에 포함
  - `test_hwp5_extract_fixture` — 실제 HWP fixture → `ok`, 텍스트에 fixture 문서에 실제로 있는 단어(파일 확인 후 기입) 포함
  - `test_pdf_extract_fixture`
  - `test_convert_failures_do_not_raise` — 랜덤 바이트 `.hwp`, 빈 `.pdf`, `.docx`(미지원) → 모두 `ok=False`, `error` 비어있지 않음, 예외 없음
  - `test_zip_uses_pick_rfp_order`
  - `test_pick_rfp_order` — `["붙임1_보안서약서.hwp","제안요청서_최종.hwp","과업지시서.pdf"]` → `["제안요청서_최종.hwp","과업지시서.pdf","붙임1_보안서약서.hwp"]`
  - `test_excerpt_prioritizes_sections` / `test_excerpt_short_text_unchanged`
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현.
- [ ] **Step 4:** PASS 확인.
- [ ] **Step 5:** 커밋 `feat: HWP/HWPX/PDF conversion and RFP excerpt`.

---

### Task 6: 첨부 다운로드

**Files:**
- Create: `scripts/g2b_scout/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `Notice`, `convert.convert`, `convert.pick_rfp`, `excerpt.make_excerpt`
- Produces:
  - `safe_filename(name: str, max_len: int = 120) -> str` — URL 디코딩, Windows 금지문자(`<>:"/\|?*` 및 제어문자) `_`로, 확장자 보존하며 자름
  - `fetch_documents(notice: Notice, out_dir: Path, session=requests) -> DocResult` — `out_dir/<key>/`에 첨부 저장, `pick_rfp` 순서로 변환, 성공한 첫 문서의 발췌를 `out_dir/<key>/excerpt.txt`에 저장
  - `DocResult(ok: bool, rfp_path: Path|None, rfp_name: str|None, excerpt_path: Path|None, error: str|None)` (models.py에 추가)
  - 다운로드 응답이 HTML이면(로그인 페이지 등) 실패로 처리. 파일당 타임아웃 60초, 1회 재시도.

- [ ] **Step 1: 실패하는 테스트 작성** — `test_safe_filename` (`"%EC%A0%9C%EC%95%88:요청서?.hwp"` → `"제안_요청서_.hwp"`, 300자 이름 → 길이 ≤120이고 `.hwp`로 끝남), `test_fetch_html_response_is_failure`, `test_fetch_picks_rfp_and_writes_excerpt` (가짜 session이 HWPX 바이트 반환).
- [ ] **Step 2:** FAIL. **Step 3:** 구현. **Step 4:** PASS.
- [ ] **Step 5:** 커밋 `feat: attachment download`.

---

### Task 7: 노션 클라이언트

**Prerequisite (사용자):** 노션 내부 통합 생성 → 토큰을 `.env`의 `NOTION_TOKEN`에; DB를 만들 팀 페이지를 통합에 공유하고 페이지 URL 제공.

`Notion-Version`은 `2022-06-28`로 고정한다(우리가 만드는 DB는 단일 데이터소스라 `databases/{id}/query`가 동작). 구현 시 developers.notion.com에서 이 버전의 file_uploads 지원을 확인하고, 안 되면 최신 버전 + `data_sources` 엔드포인트로 바꾸고 이 문단을 갱신한다.

**Files:**
- Create: `scripts/g2b_scout/notion_db.py`
- Test: `tests/test_notion_db.py`

**Interfaces:**
- Consumes: `Notice`, `Analysis`(Task 8에서 정의하지만 여기서는 dict로 받음), `DocResult`
- Produces:
  - `class NotionClient(token: str, session=requests)`
    - `create_database(parent_page_id: str, title: str = "나라장터 추천 공고") -> str` — 스펙 6.5 속성 전체 생성, select 옵션 포함
    - `existing_keys(database_id: str) -> set[str]` — `공고번호` 전 페이지 순회(`has_more`/`next_cursor`), 필터 없이 전체(행 수천 개 수준 가정)
    - `upload_file(path: Path, max_mb: int) -> str | None` — 크기 초과면 업로드 시도 없이 None; 생성→send→id; 실패 시 None
    - `create_entry(database_id: str, notice: Notice, analysis: dict, doc: DocResult, file_upload_id: str|None, collector: str) -> str` — page id 반환
  - 순수 함수: `build_properties(notice, analysis, doc, file_upload_id, collector, today: date) -> dict`, `build_blocks(analysis: dict, doc: DocResult) -> list[dict]`
  - 노션 API 429는 `Retry-After`만큼 기다린 뒤 최대 3회 재시도

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_build_properties_fit3` — 적합도 `★★★`, 상태 `검토전`, 구분 `본공고`, 공고번호 = `notice.key`, 예산 number
  - `test_build_properties_fit1_auto_excluded` — 상태 `자동제외`
  - `test_build_properties_file_fallback_link` — `file_upload_id=None`이고 첨부 URL 있으면 `제안요청서`가 `external` 파일(이름=원래 첨부명)
  - `test_build_properties_rfp_failed` — `doc.ok=False` → `RFP 분석` `실패`
  - `test_build_blocks_failed_warning` — `doc.ok=False`면 첫 블록이 `⚠ 제안요청서 변환 실패 — 원문 직접 확인 필요` callout
  - `test_build_blocks_sections` — 개요/주요 요구사항/우리 팀과 맞는 이유/안 맞는 부분/참가 자격·리스크/평가 방식 제목 순서
  - `test_existing_keys_paginates` — 가짜 session 2페이지(100+3) → 103개
  - `test_upload_skips_oversize` — 6MB 파일, max 5 → None, HTTP 호출 0회
  - 텍스트 속성은 노션 한계 2000자에서 자른다: `test_long_summary_truncated`
  - `test_revised_notice_marked` — 차수가 최초 차수(api-notes에 기록된 값, 보통 `"000"`)가 아니면 `한줄 요약` 앞에 `[정정공고] ` (스펙 6.6)
- [ ] **Step 2:** FAIL. **Step 3:** 구현. **Step 4:** PASS.
- [ ] **Step 5:** 수동 확인 — 테스트용 노션 페이지에 `create_database` 실행 → 속성 14개 확인 후 DB 삭제.
- [ ] **Step 6:** 커밋 `feat: notion client`.

---

### Task 8: CLI `scout.py` + 분석 JSON 검증

Claude와 스크립트의 계약. 모든 하위 명령은 결과를 stdout에 JSON 한 줄로 출력(Claude가 읽음), 사람용 로그는 `home()/logs/YYYYMMDD.log`.

**Files:**
- Create: `scripts/scout.py`, `scripts/g2b_scout/analysis.py`
- Test: `tests/test_analysis.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2~7 전부
- Produces (명령):
  - `scout.py doctor` → 설정·비밀·노션 접근·API 키 확인. `{"ok": bool, "problems": [str]}`
  - `scout.py setup-notion --parent-page <url|id>` → DB 생성 후 `config.yaml`의 `notion.database_id` 기록. `{"database_id": ...}`
  - `scout.py candidates` → 새 run 폴더 생성, 수집(최근 `lookback_days`)→`existing_keys`→`select_candidates`, `candidates.json`(선택분 Notice 목록) 저장. `{"run_dir", "collected", "new", "selected", "overflow"}`
  - `scout.py fetch --run <dir>` → 선택분마다 `fetch_documents`, `docs.json`(key→DocResult) 저장. `{"ok": n, "failed": n}`
  - `scout.py publish --run <dir> --key <key>` → `analysis/<key>.json` 읽어 `validate_analysis`, 업로드 직전 `existing_keys`에 키가 있으면 건너뜀, 파일 업로드→`create_entry`. `{"key", "status": "created"|"skipped_duplicate", "page_url"}`
  - `scout.py summary --run <dir>` → `{"selected", "published", "by_fit": {"3":n,"2":n,"1":n}, "rfp_failed", "overflow"}`
  - `analysis.validate_analysis(data: dict) -> dict` — 스펙 6.4 스키마. `fit`∈{1,2,3}, `summary` 비어있지 않음, `detail`의 키 7개 존재, `rfp_read` bool. 위반 시 `AnalysisError`(어떤 필드인지)
  - `collector` = 환경변수 `G2B_SCOUT_COLLECTOR` 또는 OS 사용자명

- [ ] **Step 1: 실패하는 테스트 작성** — `test_validate_ok`, `test_validate_rejects_fit_4`, `test_validate_missing_detail_key`, `test_publish_skips_duplicate` (가짜 NotionClient: existing_keys에 키 있음 → `skipped_duplicate`, create_entry 호출 0회), `test_candidates_writes_json` (가짜 API·노션 주입, `G2B_SCOUT_HOME`을 tmp_path로).
- [ ] **Step 2:** FAIL. **Step 3:** 구현 (테스트 주입을 위해 `main(argv, *, api=None, notion=None)` 형태).
- [ ] **Step 4:** `pytest -v` 전체 PASS.
- [ ] **Step 5:** 커밋 `feat: scout CLI`.

---

### Task 9: 스킬 문서 + 플러그인 매니페스트

**Files:**
- Create: `skills/g2b-rfp-scout/SKILL.md`, `references/analysis-guide.md`, `references/setup-guide.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: `SKILL.md`** — frontmatter `name: g2b-rfp-scout`, description에 트리거("나라장터 공고 찾아줘", "입찰 공고 추천", "RFP 수집", "/g2b-rfp-scout"). 본문 절차:
  1. `python <skill_dir>/scripts/scout.py doctor` — 실패 시: config 없음 → 첫 실행 인터뷰(팀명, 하는 일·역량, 대표 실적, 관심 키워드, 제외 키워드, 예산 범위, 사전규격 포함 여부)를 한 번에 하나씩 묻고 `config.yaml` 작성; 비밀 없음 → `references/setup-guide.md` 안내 후 중단; DB 없음 → `setup-notion`.
  2. `candidates` → `fetch`.
  3. 선택된 공고마다: `candidates.json`의 메타데이터와 `excerpt.txt`(없으면 메타데이터만, `rfp_read=false`)를 읽고 `references/analysis-guide.md` 기준으로 `analysis/<key>.json` 작성 → 즉시 `publish --key`. 한 건씩 반복.
  4. `summary` 결과를 사용자에게 보고(★★★ 공고명·마감일 목록, 변환 실패 수, overflow>0이면 재실행 안내).
  - 규칙: RFP를 못 읽었으면 읽은 척하지 말 것; 비밀 값 출력 금지; 무인 실행(`claude -p`)이면 질문 없이 doctor 실패 시 문제만 출력하고 종료.
- [ ] **Step 2: `analysis-guide.md`** — 스펙 6.4의 JSON 스키마(예시 1개), 적합도 기준 3단계와 경계 예시(예: "AI 기반 CCTV 장비 구매" → ★; "공공데이터 AI 플랫폼 구축(컨설팅 일부)" → ★★), `capabilities` 대비 판단하라는 지시, 실적·지역 제한·공동수급 확인 항목.
- [ ] **Step 3: `setup-guide.md`** — Python 설치 확인, `pip install -r requirements.txt`, 공공데이터포털 회원가입→두 API 활용신청→서비스키(Decoding 키 사용), 노션 통합 생성→토큰→팀 페이지에 통합 연결, `.env` 위치·형식 예시(값은 자리표시자).
- [ ] **Step 4: 매니페스트** — `plugin.json`(name `g2b-rfp-scout`, version `0.1.0`, description, skills 경로), `marketplace.json`(plugins: `[{name: "g2b-rfp-scout", source: "./"}]`). 현재 Claude Code 플러그인 문서의 스키마로 확인.
- [ ] **Step 5: 검증** — 이 저장소를 로컬 마켓플레이스로 추가(`/plugin marketplace add c:\rfp-analysis`)하고 설치 → 새 세션에서 스킬 목록에 `g2b-rfp-scout` 표시 확인.
- [ ] **Step 6:** 커밋 `feat: skill instructions and plugin manifests`.

---

### Task 10: 정기 실행, README, 실제 E2E

**Files:**
- Create: `scheduler/register-task.ps1`, `README.md`, `LICENSE` (MIT, 저작권자는 사용자에게 표기명 확인)

- [ ] **Step 1: `register-task.ps1`** — 파라미터 `-Time "08:30"`(기본), 평일 트리거로 `claude -p "/g2b-rfp-scout" --allowedTools "Bash(python:*),Read,Write"` 실행하는 작업 `g2b-rfp-scout` 등록, 출력은 `%USERPROFILE%\.g2b-rfp-scout\logs\scheduled-YYYYMMDD.log`로. `-Unregister` 스위치로 제거. (허용 도구 플래그 이름은 현재 `claude --help`로 확인)
- [ ] **Step 2: `README.md`** — 한국어 본문 + 영문 요약: 무엇을 하는지, 노션 결과 스크린샷 자리, 설치(마켓플레이스 추가·pip), 15분 설정(setup-guide 링크), 정기 실행, 설정 항목 표, 한계(스캔 PDF, 무료 노션 5MB, 동시 실행 드문 중복).
- [ ] **Step 3: E2E (사용자 키로 실제 실행)** — 새 세션에서 `/g2b-rfp-scout` 실행 → 기대: 노션 DB에 행 생성, ★★★/★★는 `검토전`, ★는 `자동제외`, 5MB 이하 RFP는 파일 첨부, 페이지 본문 섹션 존재. 즉시 한 번 더 실행 → `published 0`(중복 없음) 확인.
- [ ] **Step 4:** 결과를 사용자와 함께 보고 적합도 판단이 납득되는지 3~5건 검토, 필요하면 `analysis-guide.md` 기준 조정.
- [ ] **Step 5:** `register-task.ps1` 등록 후 `Start-ScheduledTask g2b-rfp-scout`로 1회 실행, 로그 확인.
- [ ] **Step 6:** 커밋 `docs: README, scheduler, license`. GitHub 공개 저장소 생성·푸시는 **사용자 확인 후** `gh repo create <name> --public --source . --push`.
