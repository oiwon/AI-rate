from pathlib import Path
import pandas as pd

# 파일 경로
RAW = Path("data/raw")
OUTPUT = Path("data/processed/merged.csv")

# 분석 대상: 세부 상품군 15개
TARGET_CODES = [
    "G11", "G12", "G13", "G14", "G19",
    "G21", "G22", "G23", "G29",
    "G31", "G32", "G33", "G34", "G35", "G39"
]

# T2: 불변지수, T3: 계절조정지수
TARGET_INDICES = ["T2", "T3"]

# 1. 원본 불러오기
ecos = pd.read_csv(
    RAW / "ecos_base_rate.csv",
    dtype={"TIME": str}
)
kosis = pd.read_csv(
    RAW / "kosis_retail_index.csv",
    dtype={"PRD_DE": str, "C1": str, "ITM_ID": str}
)

print(f"ECOS 원본: {len(ecos)}건")
print(f"KOSIS 원본: {len(kosis)}건")

# 2. 필요한 상품군과 지수 선택
selected = kosis[
    kosis["C1"].isin(TARGET_CODES)
    & kosis["ITM_ID"].isin(TARGET_INDICES)
].copy()

print(f"KOSIS 선별 후: {len(selected)}건")
print(f"선별 제외: {len(kosis) - len(selected)}건")

# 3. 연월 및 숫자 형식 정리
ecos["year_month"] = ecos["TIME"]
selected["year_month"] = selected["PRD_DE"]

ecos["base_rate"] = pd.to_numeric(
    ecos["DATA_VALUE"], errors="coerce"
)
selected["retail_index"] = pd.to_numeric(
    selected["DT"], errors="coerce"
)

# 결측 및 중복 검증
if ecos["year_month"].duplicated().any():
    raise ValueError("ECOS에 중복 연월이 있습니다.")

if selected.duplicated(
    ["year_month", "C1", "ITM_ID"]
).any():
    raise ValueError("KOSIS에 중복 데이터가 있습니다.")

if ecos["base_rate"].isna().any():
    raise ValueError("ECOS 기준금리에 결측값이 있습니다.")

if selected["retail_index"].isna().any():
    raise ValueError("KOSIS 판매지수에 결측값이 있습니다.")

# 4. 연월 기준 다대일 결합
merged = selected.merge(
    ecos[["year_month", "base_rate"]],
    on="year_month",
    how="left",
    validate="many_to_one",
    indicator=True
)

success = (merged["_merge"] == "both").sum()
failure = (merged["_merge"] == "left_only").sum()

print(f"결합 성공: {success}건")
print(f"결합 실패: {failure}건")

# 5. 결과 저장
merged = merged.drop(columns=["_merge"])
merged = merged.sort_values(
    ["year_month", "C1", "ITM_ID"]
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
merged.to_csv(
    OUTPUT, index=False, encoding="utf-8-sig"
)

print(f"최종 저장 건수: {len(merged)}건")
print(f"저장 위치: {OUTPUT}")
