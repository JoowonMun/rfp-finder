# 처음 설정하기 (약 15분)

설정 파일과 키는 모두 **내 PC의 설정 폴더**에 둔다: `%USERPROFILE%\.g2b-rfp-scout\`
(예: `C:\Users\홍길동\.g2b-rfp-scout\`) 저장소나 대화창에는 절대 키를 붙여넣지 않는다.

## 0. Python 패키지 설치

Python 3.10 이상이 필요하다. 명령 프롬프트에서:

```
python --version
pip install -r "<플러그인 폴더>\requirements.txt"
```

## 1. 공공데이터포털 서비스키

1. [data.go.kr](https://www.data.go.kr) 회원가입·로그인
2. 아래 두 API를 검색해 각각 **활용신청** (개발계정, 자동승인)
   - 조달청_나라장터 입찰공고정보서비스
   - 조달청_나라장터 사전규격정보서비스
3. 마이페이지 → 개발계정 → 신청한 API 상세 → **일반 인증키(Decoding)** 복사
   - 신청 직후 1~2시간은 "등록되지 않은 서비스키" 오류가 날 수 있다.

## 2. 노션 통합 토큰

1. [notion.so/profile/integrations](https://www.notion.so/profile/integrations) → **새 통합** (내부 통합)
2. 이름 예: `g2b-rfp-scout`, 워크스페이스: 팀 워크스페이스
3. 기능에서 콘텐츠 읽기·업데이트·삽입 허용 → 저장 후 **내부 통합 시크릿** 복사

## 3. 팀 페이지에 통합 연결

공고 DB를 둘 노션 페이지에서 오른쪽 위 `•••` → **연결(Connections)** → 방금 만든 통합 선택.
(팀원 중 한 명이 DB를 만들면, 다른 팀원은 자기 통합을 그 DB 페이지에 연결만 하면 된다.)

## 4. `.env` 파일 만들기

`%USERPROFILE%\.g2b-rfp-scout\.env` 를 메모장으로 만들고:

```
DATA_GO_KR_SERVICE_KEY=여기에_Decoding_키
NOTION_TOKEN=여기에_노션_시크릿
# 입찰공고 서비스 키가 따로 있을 때만 (없으면 위 키 사용)
DATA_GO_KR_BID_SERVICE_KEY=
```

- `=` 바로 뒤에 **같은 줄로** 붙여넣는다. 따옴표·공백 없이.

## 5. 첫 실행

Claude Code에서 `/g2b-rfp-scout` 또는 "나라장터 공고 찾아줘".
- 팀 설정(config.yaml)은 Claude가 질문하며 만들어 준다.
- 노션 DB가 없으면 DB를 둘 페이지 URL을 물어보고 만들어 준다. 이미 팀 DB가 있으면 그 DB의 ID를 `config.yaml`의 `notion.database_id`에 넣는다.
