# rfp-finder — 나라장터 공고 추천 스킬

나라장터(조달청)에 올라오는 **용역 입찰공고와 사전규격**을 모아서, **제안요청서(HWP·HWPX·PDF) 본문까지 읽고**, 우리 팀 역량에 맞는 공고를 골라 **노션 표**에 쌓아주는 [Claude Code](https://claude.com/claude-code) 스킬입니다.

## 무엇을 해주나

1. **수집** — 공공데이터포털 조달청 OpenAPI로 최근 30일 등록된 공고 중 마감이 안 지난 것을 모읍니다(하루 수천 건).
2. **1차 거르기** — 관심·제외 키워드, 예산, 마감일로 스크립트가 걸러냅니다. 같은 입력이면 항상 같은 결과.
3. **제안요청서 읽기** — 첨부를 내려받아 텍스트로 변환합니다. HWP5는 직접 파싱, HWPX는 XML, PDF는 텍스트 추출. 스캔본이나 **다른 공고 문서가 잘못 첨부된 경우**도 감지합니다.
4. **판단** — Claude가 RFP를 팀 소개와 비교해 적합도(★~★★★)를 매기고 요약합니다. 못 읽은 문서는 읽은 척하지 않습니다.
5. **노션 기록** — ★★ 이상만 팀 노션 표에 올리고, 각 공고 페이지는 대시보드 형태로 만듭니다. 중복은 자동으로 건너뜁니다.

```
┌─ 🎯 적합도 ─┐ ┌─ 💰 예산 ──┐ ┌─ ⏰ 마감 ──┐ ┌─ 📊 평가 ──┐
│  ★★★       │ │  4.2억     │ │  D-23      │ │ 기술 90    │
│ 바로 검토   │ │  6개월     │ │ 01.15(금)  │ │ 가격 10    │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
💬 생성형 AI 도입 ISP — 팀 AX 컨설팅과 직접 일치
📌 사업 개요 (발주·내용·기간·예산·계약 표)
📋 주요 요구사항 (번호 + 세부 불릿)
✅ 맞는 점            | ⚠️ 안 맞는 점·리스크
☑ 참가 자격 체크리스트 · 📊 평가 방식
```

## 설치

필요한 것: Claude Code, Python 3.10+, 공공데이터포털 계정, 노션 워크스페이스

```
# Claude Code 안에서
/plugin marketplace add JoowonMun/rfp-finder
/plugin install rfp-finder@rfp-finder
```

```
# 명령 프롬프트에서 (플러그인 폴더의 requirements.txt)
pip install -r requirements.txt
```

키 발급과 노션 연결은 [설정 가이드](skills/rfp-finder/references/setup-guide.md)를 따라 하면 15분이면 됩니다. [`.env.example`](skills/rfp-finder/.env.example)을 `%USERPROFILE%\.rfp-finder\.env`로 복사해 키를 채우면 되고, 이 파일은 저장소에 올라가지 않습니다.

## 사용

Claude Code에서 `/rfp-finder` 또는 "나라장터 공고 찾아줘".

- 첫 실행이면 팀 소개·관심 키워드 등을 물어보며 설정 파일을 만들어 줍니다.
- 노션 DB가 없으면 페이지 URL을 물어보고 만들어 줍니다.

### 매일 아침 자동 실행 (Windows)

```powershell
.\scheduler\register-task.ps1                  # 평일 08:30
.\scheduler\register-task.ps1 -Time "07:50"
.\scheduler\register-task.ps1 -Unregister
```

## 설정 (`%USERPROFILE%\.rfp-finder\config.yaml`)

| 항목 | 설명 | 기본값 |
|---|---|---|
| `team.capabilities` | 팀이 잘하는 일. **적합도 판단의 핵심**이니 구체적으로 | (필수) |
| `filters.include_keywords` | 제목에 하나라도 있어야 후보가 됨 | (필수) |
| `filters.exclude_keywords` | 포함 키워드 없이 이것만 있으면 탈락, 같이 있으면 뒤로 밀림 | `[]` |
| `filters.priority_keywords` | 제목에 있으면 가장 먼저 분석 (예: ISP, 전략, 컨설팅) | `[]` |
| `filters.budget_min_krw` / `budget_max_krw` | 예산 범위 (미기재 공고는 통과) | 없음 |
| `filters.min_days_to_deadline` | 본공고 마감까지 최소 남은 일수 | 5 |
| `filters.include_pre_spec` | 사전규격 포함 | true |
| `collect.lookback_days` | 최근 N일 등록 공고를 조회 | 30 |
| `collect.max_per_run` | 한 번에 분석할 공고 수 (Claude 사용량과 비례) | 15 |
| `notion.max_upload_mb` | 노션 파일 업로드 한도 (무료 5MB) | 5 |

전체 예시: [config.example.yaml](skills/rfp-finder/config.example.yaml)

## 노션 표 보기 다듬기 (한 번만)

노션 API로는 표의 보기 설정을 바꿀 수 없어 직접 설정합니다.

1. 표 오른쪽 위 `•••` → **속성** → 구분·제안요청서·원문 링크·RFP 분석·공고번호·수집일을 👁 숨기기
2. 남은 칸 순서: 공고명 → 마감일 → 발주기관 → 적합도 → 예산 → 한줄 요약
3. **정렬** → 마감일 오름차순
4. (선택) **보기 추가** → 달력(마감일 기준), 차트(적합도별 개수)

## 한계

- 스캔본 PDF, 암호·배포용 HWP는 읽지 못합니다(노션에 "원문 직접 확인 필요"로 표시).
- 노션은 HWP 파일 첨부를 받지 않아 HWP는 나라장터 다운로드 링크로 들어갑니다. 무료 요금제는 5MB 초과 파일도 링크로 대체됩니다.
- ★(자동제외) 기록은 실행한 PC에만 남습니다. 여러 명이 따로 돌리면 ★ 공고를 사람마다 한 번씩 다시 분석합니다.
- 두 사람이 정확히 동시에 실행하면 드물게 중복 행이 생길 수 있습니다.

## 구조

```
skills/rfp-finder/
  SKILL.md                 Claude가 따르는 실행 절차
  references/              적합도 판단 지침, 설정 가이드
  scripts/scout.py         수집·다운로드·변환·노션 업로드 CLI (Claude가 호출)
  scripts/rfp_finder/      API 클라이언트, 필터, HWP/PDF 변환, 노션 클라이언트
  config.example.yaml      팀 설정 예시
  .env.example             키 설정 예시 (값은 비어 있음)
scheduler/                 Windows 작업 스케줄러 등록
tests/                     pytest (실제 나라장터 응답·문서 샘플 포함)
docs/                      설계 문서, 구현 계획, API 확인 기록
```

반복 작업은 스크립트가 결정적으로 처리하고, 판단(적합도·요약)만 Claude가 합니다. 둘은 실행 폴더의 JSON 파일로 주고받습니다.

## 개발

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

---

## English summary

**rfp-finder** is a Claude Code skill for Korean public-procurement bidding. It pulls open service tenders and pre-specifications from the KONEPS (나라장터) OpenAPI, downloads the RFP attachments and extracts their text (native HWP5/HWPX parsing, PDF), lets Claude score each notice against your team's capabilities, and writes the promising ones to a Notion database with a dashboard-style page per notice. Deterministic work (collection, filtering, conversion, Notion I/O, de-duplication) lives in a tested Python CLI; Claude only does the judgment. Setup takes about 15 minutes: a data.go.kr service key, a Notion internal integration, and a short interview that writes your team profile.

## License

MIT
