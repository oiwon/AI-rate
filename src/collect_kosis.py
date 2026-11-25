"""KOSIS 재별 및 상품군별 소매판매액지수(월별)를 수집해 data/raw에 CSV로 저장한다.

원본은 모든 상품군·모든 지수 종류를 그대로 저장한다.
분석 대상 15개 상품군 × 불변·계절조정지수 선별은 clean_merge.py에서 한다.
"""

import os
import sys
from datetime import date

import pandas as pd
import requests
from dotenv import load_dotenv

API_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ORG_ID = "101"          # 통계청
TBL_ID = "DT_1K41012"   # 재별 및 상품군별 소매판매액지수 (2020=100)
CYCLE = "M"             # 월별
START_YM = "201501"
END_YM = "202609"
SAVE_PATH = "data/raw/kosis_retail_index.csv"
TIMEOUT_SEC = 60
KEEP_COLUMNS = ["PRD_DE", "C1", "C1_NM", "ITM_ID", "ITM_NM", "DT", "UNIT_NM", "LST_CHN_DE"]


def load_key() -> str:
    """.env에서 KOSIS 인증키를 읽는다. 없으면 프로그램을 멈춘다."""
    load_dotenv()
    key = os.getenv("KOSIS_API_KEY")
    if not key:
        sys.exit("KOSIS_API_KEY가 없습니다. .env.example을 복사해 .env를 만들고 키를 넣어 주세요.")
    return key


def fetch_retail_index(key: str) -> list[dict]:
    """KOSIS API를 호출해 모든 상품군·지수 종류의 행 목록을 돌려준다."""
    params = {
        "method": "getList",
        "apiKey": key,
        "orgId": ORG_ID,
        "tblId": TBL_ID,
        "itmId": "ALL",     # 지수 종류 전체 (T1 경상, T2 불변, T3 계절조정)
        "objL1": "ALL",     # 상품군 전체
        "prdSe": CYCLE,
        "startPrdDe": START_YM,
        "endPrdDe": END_YM,
        "format": "json",
        "jsonVD": "Y",
    }
    try:
        res = requests.get(API_URL, params=params, timeout=TIMEOUT_SEC)
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError) as e:
        # 오류 메시지에 URL(=키)이 들어갈 수 있어 예외 종류만 출력한다
        sys.exit(f"KOSIS 호출 실패: {type(e).__name__}")

    # 정상 응답은 목록, 오류 응답은 {"err": ..., "errMsg": ...} 형태
    if isinstance(data, dict):
        sys.exit(f"KOSIS 오류 {data.get('err')}: {data.get('errMsg')}")
    return data


def save_raw(rows: list[dict]) -> pd.DataFrame:
    """필요한 열만 골라 원본 문자열 그대로 CSV로 저장한다. 행은 빼지 않는다."""
    df = pd.DataFrame(rows)[KEEP_COLUMNS]
    df["collected_at"] = date.today().isoformat()
    df.to_csv(SAVE_PATH, index=False, encoding="utf-8-sig")
    return df


def main() -> None:
    key = load_key()
    rows = fetch_retail_index(key)
    df = save_raw(rows)
    print(f"KOSIS 소매판매액지수 {len(df)}건 저장: {SAVE_PATH}")
    print(f"기간: {df['PRD_DE'].min()} ~ {df['PRD_DE'].max()} ({df['PRD_DE'].nunique()}개월)")
    print(f"상품군: {df['C1'].nunique()}개")
    for itm_id, count in df.groupby("ITM_ID").size().items():
        print(f"  {itm_id}: {count}건")


if __name__ == "__main__":
    main()
