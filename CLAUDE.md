# AI-rate 프로젝트 규칙

이 파일은 Claude Code가 이 폴더에서 작업을 시작할 때 자동으로 읽는 안내문입니다.
**인증키는 이 파일에 절대 적지 않습니다.**

## 프로젝트
- AI개발환경의이해 기말 프로젝트(A조): 기준금리 변화에 대한 상품군별 소비 민감도 대시보드
- 요구사항은 `docs/요건정의서.md`를 따릅니다. 문서와 다르게 만들어야 하면 먼저 이유를 설명하고 승인을 받습니다.
- 사용자는 프로그래밍 초보자입니다. 무엇을, 왜 하려는지 쉬운 말로 먼저 설명합니다.

## 폴더 구조
- `src/`: 코드 (collect_ecos.py, collect_kosis.py, clean_merge.py, 이후 분석·서버·화면)
- `data/raw/`: API 응답을 CSV로 저장한 원본. 행을 빼거나 값을 바꾸지 않습니다.
- `data/processed/`: 정리·결합된 CSV
- `data/sample/`: 인증키가 없을 때 쓰는 샘플 데이터
- `docs/`: 요건정의서, 건수 검증표
- `tests/`: 테스트

## 보안 (항상 지킬 것)
- 인증키는 `.env`의 `ECOS_API_KEY`, `KOSIS_API_KEY`에서만 읽습니다. 코드·파일·출력에 키 값을 쓰지 않습니다.
- 키 값을 화면에 출력하는 명령(예: `Get-Content .env`, `type .env`, `echo $env:ECOS_API_KEY`)을 실행하지 않습니다. 필요하면 키가 설정되어 있는지 여부만 확인합니다.
- ECOS는 URL 경로에, KOSIS는 URL 파라미터(apiKey)에 인증키가 들어갑니다. 두 API 모두 요청 URL을 print·log·예외 메시지로 출력하지 않습니다(`raise_for_status()`의 기본 메시지 포함).
- `.env` 파일의 내용을 읽거나 출력하지 않습니다.
- `.gitignore`의 규칙을 지우거나 바꾸지 않습니다.

## 실행 환경
- Windows + PowerShell(VS Code 터미널), Python 3. 필요한 패키지는 `requirements.txt`에 적습니다.
- 수집 파일에는 수집 일자(collected_at, YYYY-MM-DD)를 기록합니다. 화면에 "마지막 수집 일자"를 보여 줄 때 씁니다.
- CSV는 엑셀에서 한글이 깨지지 않도록 utf-8-sig로 저장합니다.
- 가상환경: 처음 한 번 `python -m venv .venv` 후 `.venv\Scripts\python.exe -m pip install -r requirements.txt`
- 실행: 모든 명령은 프로젝트 맨 위 폴더(AI-rate)에서 가상환경의 파이썬으로 실행합니다(코드의 경로가 이 폴더 기준). 아래 순서대로 실행합니다.
    1. .venv\Scripts\python.exe src/collect_ecos.py
    2. .venv\Scripts\python.exe src/collect_kosis.py
    3. .venv\Scripts\python.exe src/clean_merge.py

## 작업 방식
- 코드를 만들기 전에 계획을 설명하고 승인을 기다립니다.
- `data/raw`와 `data/processed`, 건수 검증표는 실제 API로 받은 데이터로만 만듭니다. API 호출이 실패해도 임의의 데이터를 만들어 채우지 않고, 실패 원인을 보고합니다.
- 각 단계에서 몇 건을 받고, 몇 건을 제거했고, 몇 건이 남았는지 출력합니다(건수 검증표에 사용).
- "완료"라고 말하기 전에 실제 파일을 열어 요구사항과 대조하고, 근거(코드 줄 번호, 실행 결과)를 함께 보고합니다.
