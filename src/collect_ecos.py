"""ECOS 한국은행 기준금리(월별)를 수집해 data/raw에 CSV로 저장한다."""

import os
import sys
from datetime import date

import pandas as pd
import requests
from dotenv import load_dotenv

STAT_CODE = "722Y001"   # 한국은행 기준금리 및 여수신금리
ITEM_CODE = "0101000"   # 한국은행 기준금리
CYCLE = "M"             # 월별
START_YM = "201501"
END_YM = "202609"
SAVE_PATH = "data/raw/ecos_base_rate.csv"
TIMEOUT_SEC = 10


def load_key() -> str:
    """.env에서 ECOS 인증키를 읽는다. 없으면 프로그램을 멈춘다."""
    load_dotenv()
    key = os.getenv("ECOS_API_KEY")
    if not key:
        sys.exit("ECOS_API_KEY가 없습니다. .env.example을 복사해 .env를 만들고 키를 넣어 주세요.")
    return key


def fetch_base_rate(key: str) -> list[dict]:
    """ECOS API를 호출해 기준금리 행 목록을 돌려준다."""
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/"
        f"{STAT_CODE}/{CYCLE}/{START_YM}/{END_YM}/{ITEM_CODE}"
    )
    try:
        res = requests.get(url, timeout=TIMEOUT_SEC)
        res.raise_for_status()
    except requests.RequestException as e:
        # 오류 메시지에 URL(=키)이 들어갈 수 있어 예외 종류만 출력한다
        sys.exit(f"ECOS 호출 실패: {type(e).__name__}")

    data = res.json()
    if "RESULT" in data:
        result = data["RESULT"]
        sys.exit(f"ECOS 오류 {result['CODE']}: {result['MESSAGE']}")
    return data["StatisticSearch"]["row"]


def save_raw(rows: list[dict]) -> pd.DataFrame:
    """필요한 열만 골라 원본 문자열 그대로 CSV로 저장한다."""
    df = pd.DataFrame(rows)[["TIME", "DATA_VALUE", "UNIT_NAME"]]
    df["collected_at"] = date.today().isoformat()
    df.to_csv(SAVE_PATH, index=False, encoding="utf-8-sig")
    return df


def main() -> None:
    key = load_key()
    rows = fetch_base_rate(key)
    df = save_raw(rows)
    print(f"ECOS 기준금리 {len(df)}건 저장: {SAVE_PATH}")
    print(f"기간: {df['TIME'].iloc[0]} ~ {df['TIME'].iloc[-1]}")


if __name__ == "__main__":
    main()