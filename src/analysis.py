"""기준금리와 상품군별 소매판매지수의 관계를 분석하는 함수 모음.

FastAPI 서버와 Streamlit 화면은 이 파일의 함수를 불러서 사용한다.
모든 경로는 프로젝트 맨 위 폴더(기말과제) 기준이다.
"""

from pathlib import Path

import pandas as pd

# 데이터 파일 위치: 실제 결합 결과가 없으면 샘플을 쓴다
MERGED_PATH = Path("data/processed/merged.csv")
SAMPLE_PATH = Path("data/sample/merged_sample.csv")

# 상품군 코드 앞 두 글자로 재 구분 꼬리표를 붙인다 (가설 H1 확인용)
GROUP_BY_PREFIX = {"G1": "내구재", "G2": "준내구재", "G3": "비내구재"}

# 분석에 쓰는 열
COLUMNS = ["year_month", "C1", "C1_NM", "ITM_ID", "retail_index", "base_rate", "collected_at"]


def clean_numbers(data):
    """판매지수와 기준금리를 숫자로 바꾸고, 바꿀 수 없는 행은 뺀다.

    반환: (정리된 표, 뺀 행 수)
    """
    result = data.copy()
    result["retail_index"] = pd.to_numeric(result["retail_index"], errors="coerce")
    result["base_rate"] = pd.to_numeric(result["base_rate"], errors="coerce")

    failed = result["retail_index"].isna() | result["base_rate"].isna()
    return result[~failed].reset_index(drop=True), int(failed.sum())


def load_data(merged_path=MERGED_PATH, sample_path=SAMPLE_PATH):
    """결합 CSV를 읽는다. 실제 결합 파일이 없으면 샘플 파일을 읽는다.

    반환: (데이터 표, 정보 딕셔너리)
    """
    if merged_path.exists():
        path, source = merged_path, "실제 데이터"
    elif sample_path.exists():
        path, source = sample_path, "샘플 데이터"
    else:
        raise FileNotFoundError(
            "데이터 파일이 없습니다. 수집·결합 코드를 먼저 실행하거나 data/sample 폴더를 확인하세요."
        )

    raw = pd.read_csv(
        path,
        encoding="utf-8-sig",
        dtype={"year_month": str, "C1": str, "ITM_ID": str},
    )
    data, dropped = clean_numbers(raw[COLUMNS])
    data["group"] = data["C1"].str[:2].map(GROUP_BY_PREFIX)

    info = {
        "source": source,
        "path": str(path),
        "collected_at": data["collected_at"].max(),
        "rows": len(data),
        "dropped": dropped,
    }
    return data, info


def previous_year(year_month):
    """연월(YYYYMM 글자)을 1년 전 같은 달로 바꾼다. 예: '202509' → '202409'"""
    return (year_month.astype(int) - 100).astype(str)


def add_yoy(data):
    """판매지수 전년동월비(%)를 계산해 sales_yoy 열로 붙인다.

    전년동월비 = (당월 지수 ÷ 전년 동월 지수 − 1) × 100
    1년 전 값이 없는 달(2015년)은 빈 값(NaN)으로 남는다.
    """
    result = data.copy()
    result["prev_month"] = previous_year(result["year_month"])

    last_year = result[["year_month", "C1", "ITM_ID", "retail_index"]].rename(
        columns={"year_month": "prev_month", "retail_index": "prev_index"}
    )
    result = result.merge(last_year, on=["prev_month", "C1", "ITM_ID"], how="left")

    result["sales_yoy"] = (result["retail_index"] / result["prev_index"] - 1) * 100
    return result.drop(columns="prev_month")


def rate_table(data):
    """월별 기준금리와 변화폭(%p)을 담은 표를 만든다.

    변화폭 = 당월 기준금리 − 전년 동월 기준금리
    """
    rates = (
        data[["year_month", "base_rate"]]
        .drop_duplicates()
        .sort_values("year_month")
        .reset_index(drop=True)
    )
    if rates["year_month"].duplicated().any():
        raise ValueError("같은 연월에 기준금리가 2개 이상 있습니다. 결합 파일을 확인하세요.")

    rates["prev_month"] = previous_year(rates["year_month"])
    last_year = rates[["year_month", "base_rate"]].rename(
        columns={"year_month": "prev_month", "base_rate": "prev_rate"}
    )
    rates = rates.merge(last_year, on="prev_month", how="left")

    rates["rate_change"] = (rates["base_rate"] - rates["prev_rate"]).round(2)
    return rates.drop(columns="prev_month")


# 코로나19 시기 (제외 옵션에 사용)
COVID_START, COVID_END = "202001", "202112"

# 상관계수를 구할 금리 열과 화면에 보일 이름
RATE_TYPES = {"base_rate": "수준", "rate_change": "변화폭"}

# 짝이 이보다 적으면 상관계수를 구하지 않는다
MIN_PAIRS = 3

LAG_COLUMNS = ["C1", "C1_NM", "group", "rate_type", "lag", "corr", "pairs"]


def add_months(year_month, months):
    """연월(YYYYMM 글자)에 개월 수를 더한다. 예: '202511' + 3 → '202602'"""
    number = year_month.astype(int)
    total = (number // 100) * 12 + (number % 100 - 1) + months
    return ((total // 12) * 100 + total % 12 + 1).astype(str)


def in_period(year_month, start, end):
    """연월이 start~end 안에 있으면 True"""
    return (year_month >= start) & (year_month <= end)


def lag_correlations(sales, rates, max_lag, start, end, exclude_covid=False):
    """상품군별로 금리(t월)와 판매 전년동월비(t+k월)의 상관계수를 k=0~max_lag까지 구한다.

    금리 수준과 변화폭 각각 계산한다. 금리 달과 판매 달이 모두 start~end 안에 있는 짝만 쓴다.
    """
    rows = []
    for k in range(max_lag + 1):
        # 금리 t월을 판매 t+k월 옆에 붙이기 위해, 금리 표에 "짝지을 판매 달"을 만든다
        shifted = rates.rename(columns={"year_month": "rate_month"})
        shifted["sales_month"] = add_months(shifted["rate_month"], k)

        # 판매 표에도 같은 달 금리(base_rate)가 있어서, 판매 쪽은 필요한 열만 남기고 붙인다
        pairs = sales[["year_month", "C1", "C1_NM", "group", "sales_yoy"]].merge(
            shifted[["rate_month", "sales_month", "base_rate", "rate_change"]],
            left_on="year_month",
            right_on="sales_month",
        )
        keep = in_period(pairs["rate_month"], start, end) & in_period(pairs["sales_month"], start, end)
        if exclude_covid:
            keep &= ~in_period(pairs["rate_month"], COVID_START, COVID_END)
            keep &= ~in_period(pairs["sales_month"], COVID_START, COVID_END)
        pairs = pairs[keep]

        for (code, name, group), part in pairs.groupby(["C1", "C1_NM", "group"]):
            for column, label in RATE_TYPES.items():
                valid = part[["sales_yoy", column]].dropna()
                corr = valid["sales_yoy"].corr(valid[column]) if len(valid) >= MIN_PAIRS else float("nan")
                rows.append({
                    "C1": code, "C1_NM": name, "group": group, "rate_type": label,
                    "lag": k, "corr": corr, "pairs": len(valid),
                })
    return pd.DataFrame(rows, columns=LAG_COLUMNS)


RANK_COLUMNS = ["rate_type", "rank", "C1", "C1_NM", "group", "lag", "corr", "pairs"]


def sensitivity_ranking(lags):
    """상품군마다 상관계수 절댓값이 가장 큰 시차를 대표값으로 뽑고, 절댓값이 큰 순으로 순위를 매긴다.

    금리 기준(수준, 변화폭)마다 따로 순위를 매긴다. 상관계수가 빈 값인 행은 뺀다.
    """
    valid = lags.dropna(subset=["corr"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=RANK_COLUMNS)

    valid["abs_corr"] = valid["corr"].abs()
    # 절댓값이 같으면 더 짧은 시차를 대표값으로 쓴다
    best = (
        valid.sort_values(["abs_corr", "lag"], ascending=[False, True])
        .drop_duplicates(["C1", "rate_type"])
        .sort_values(["rate_type", "abs_corr"], ascending=[True, False])
    )
    best["rank"] = best.groupby("rate_type").cumcount() + 1
    return best[RANK_COLUMNS].reset_index(drop=True)


HIKE_CUT_COLUMNS = ["C1", "C1_NM", "group", "hike_avg", "cut_avg", "hike_months", "cut_months"]


def hike_cut_average(sales, rates, start, end, exclude_covid=False):
    """금리 인상기(변화폭>0)와 인하기(변화폭<0)의 판매 전년동월비 평균을 상품군별로 구한다.

    변화폭이 0인 달(보합월)은 어느 쪽에도 넣지 않는다.
    """
    merged = sales[["year_month", "C1", "C1_NM", "group", "sales_yoy"]].merge(
        rates[["year_month", "rate_change"]], on="year_month"
    )
    keep = (
        in_period(merged["year_month"], start, end)
        & merged["sales_yoy"].notna()
        & merged["rate_change"].notna()
    )
    if exclude_covid:
        keep &= ~in_period(merged["year_month"], COVID_START, COVID_END)
    merged = merged[keep]

    keys = ["C1", "C1_NM", "group"]
    hike = merged[merged["rate_change"] > 0].groupby(keys)["sales_yoy"].agg(
        hike_avg="mean", hike_months="count"
    )
    cut = merged[merged["rate_change"] < 0].groupby(keys)["sales_yoy"].agg(
        cut_avg="mean", cut_months="count"
    )
    result = hike.join(cut, how="outer").reset_index()
    result[["hike_months", "cut_months"]] = result[["hike_months", "cut_months"]].fillna(0).astype(int)
    return result.reindex(columns=HIKE_CUT_COLUMNS)


def subject_particle(word):
    """단어 끝 글자에 받침이 있으면 '이', 없으면 '가'를 붙인다. 예: 승용차가, 음식료품이"""
    last = word[-1]
    if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 != 0:
        return word + "이"
    return word + "가"


def strength_word(corr):
    """상관계수 절댓값의 크기를 말로 바꾼다 (0.3 미만 약한, 0.5 미만 보통, 그 이상 강한)"""
    size = abs(corr)
    if size < 0.3:
        return "약한"
    if size < 0.5:
        return "보통 수준의"
    return "강한"


def summary_text(ranking, rate_type="변화폭"):
    """민감도 순위 1위 상품군으로 결과 요약 문장을 만든다."""
    top = ranking[ranking["rate_type"] == rate_type]
    if top.empty:
        return "선택한 조건으로 계산할 수 있는 결과가 없습니다. 기간을 늘리거나 조건을 바꿔 보세요."

    row = top.iloc[0]
    when = "같은 달" if row["lag"] == 0 else f"{row['lag']}개월 뒤"
    # 수준은 "금리가 높은 시기", 변화폭은 "금리가 오른 뒤"를 묻는 값이라 문장을 다르게 쓴다
    condition = "금리가 높을수록" if rate_type == "수준" else "금리가 오르면"
    if row["corr"] < 0:
        trend, period = "낮아지는", "금리 인상기"
    else:
        trend, period = "높아지는", "금리 인하기"
    return (
        f"금리 {rate_type} 기준으로 {subject_particle(row['C1_NM'])} 가장 민감합니다. "
        f"{condition} {when} 판매 전년동월비가 {trend} {strength_word(row['corr'])} 경향이 있어 "
        f"(상관계수 {row['corr']:.2f}), {period}에 재고·마케팅 조정을 먼저 검토할 상품군입니다."
    )


# 화면에 보이는 지수 이름과 KOSIS 지수 코드
INDEX_CODES = {"계절조정지수": "T3", "불변지수": "T2"}

# 최대 시차의 한계 (요건정의서: 0~12개월)
MAX_LAG_LIMIT = 12


def is_year_month(text):
    """YYYYMM 형식(6자리 숫자, 월 01~12)이면 True"""
    return isinstance(text, str) and len(text) == 6 and text.isdigit() and 1 <= int(text[4:]) <= 12


def validate_inputs(products, start, end, index_type, max_lag, all_products, first_month, last_month):
    """입력값을 검사하고, 잘못되면 안내 메시지와 함께 ValueError를 낸다."""
    if not products:
        raise ValueError("상품군을 하나 이상 선택하세요.")
    unknown = sorted(set(products) - set(all_products))
    if unknown:
        raise ValueError(f"없는 상품군 코드입니다: {', '.join(unknown)}")
    if index_type not in INDEX_CODES:
        raise ValueError("지수 종류는 계절조정지수 또는 불변지수만 고를 수 있습니다.")
    for label, value in (("시작", start), ("종료", end)):
        if not is_year_month(value):
            raise ValueError(f"{label} 연월은 YYYYMM 형식(예: 201601)으로 입력하세요.")
    if start > end:
        raise ValueError("시작 연월이 종료 연월보다 늦습니다.")
    if start < first_month or end > last_month:
        raise ValueError(f"분석 기간은 {first_month}~{last_month} 안에서 고르세요.")
    if isinstance(max_lag, bool) or not isinstance(max_lag, int) or not 0 <= max_lag <= MAX_LAG_LIMIT:
        raise ValueError(f"최대 시차는 0~{MAX_LAG_LIMIT}개월 사이의 정수로 입력하세요.")


def run_analysis(products=None, start=None, end=None, index_type="계절조정지수",
                 max_lag=6, exclude_covid=False, data=None, info=None):
    """조건을 받아 분석 결과를 한 번에 돌려준다. 서버와 화면은 이 함수를 부른다.

    products: 상품군 코드 목록 (기본값: 전체 15개)
    start, end: 분석 기간 YYYYMM (기본값: 전년동월비를 구할 수 있는 처음~끝 달)
    잘못된 입력이면 ValueError, 결과가 0건이면 빈 표와 안내 문장을 돌려준다.
    """
    if data is None:
        data, info = load_data()

    with_yoy = add_yoy(data)
    rates = rate_table(data)

    # 고를 수 있는 기간 = 전년동월비가 있는 달 (실제 데이터는 201601~202609)
    months = with_yoy.loc[with_yoy["sales_yoy"].notna(), "year_month"]
    if months.empty:
        raise ValueError("전년동월비를 계산할 수 있는 데이터가 없습니다. 데이터 파일을 확인하세요.")
    first_month, last_month = months.min(), months.max()

    all_products = sorted(data["C1"].unique())
    products = all_products if products is None else list(products)
    start = start or first_month
    end = end or last_month
    validate_inputs(products, start, end, index_type, max_lag, all_products, first_month, last_month)

    sales = with_yoy[(with_yoy["ITM_ID"] == INDEX_CODES[index_type]) & with_yoy["C1"].isin(products)]
    lags = lag_correlations(sales, rates, max_lag, start, end, exclude_covid)
    ranking = sensitivity_ranking(lags)
    hike_cut = hike_cut_average(sales, rates, start, end, exclude_covid)

    # 보합월(변화폭 0) 개수: 인상기·인하기 비교에서 뺀 달
    counted = in_period(rates["year_month"], start, end) & rates["rate_change"].notna()
    if exclude_covid:
        counted &= ~in_period(rates["year_month"], COVID_START, COVID_END)
    flat_months = int((rates.loc[counted, "rate_change"] == 0).sum())

    meta = {
        **(info or {}),
        "start": start,
        "end": end,
        "index_type": index_type,
        "max_lag": max_lag,
        "exclude_covid": exclude_covid,
        "products": len(products),
        "flat_months": flat_months,
    }
    return {
        "lag_corr": lags,
        "ranking": ranking,
        "hike_cut": hike_cut,
        "summary": {label: summary_text(ranking, label) for label in RATE_TYPES.values()},
        "meta": meta,
    }


if __name__ == "__main__":
    result = run_analysis()
    meta = result["meta"]
    print(f"데이터: {meta['source']}, 수집 일자: {meta['collected_at']}")
    print(f"조건: {meta['start']}~{meta['end']}, {meta['index_type']}, 최대 시차 {meta['max_lag']}개월, "
          f"상품군 {meta['products']}개, 코로나 제외 {meta['exclude_covid']}")
    print(f"결과: 시차별 상관 {len(result['lag_corr'])}행, 순위 {len(result['ranking'])}행, "
          f"인상기·인하기 {len(result['hike_cut'])}행, 보합월 {meta['flat_months']}개월 제외")
    print(result["summary"]["변화폭"])

    covid = run_analysis(exclude_covid=True)
    top = covid["ranking"][covid["ranking"]["rate_type"] == "변화폭"].head(5)
    print("\n[코로나 제외 시 변화폭 기준 상위 5개]")
    print(top.round(2).to_string(index=False))

    print("\n[잘못된 입력 확인]")
    wrong_inputs = [
        {"products": []},
        {"products": ["G99"]},
        {"start": "202609", "end": "201601"},
        {"start": "2016-01"},
        {"start": "201501"},
        {"max_lag": 13},
        {"index_type": "경상지수"},
    ]
    for kwargs in wrong_inputs:
        try:
            run_analysis(**kwargs)
            print(f"{kwargs} → 오류 없음 (확인 필요)")
        except ValueError as error:
            print(f"{kwargs} → {error}")

    empty = run_analysis(start="202003", end="202110", exclude_covid=True)
    print(f"\n[결과 0건 확인] 2020.03~2021.10 + 코로나 제외 → 순위 {len(empty['ranking'])}행")
    print(empty["summary"]["변화폭"])
