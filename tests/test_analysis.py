"""analysis.py 계산이 맞는지 확인하는 테스트.

실제 데이터(data/processed)는 GitHub에 올라가지 않으므로, 작은 표를 직접 만들어 확인한다.
실행: .venv\\Scripts\\python.exe -m pytest
"""

import math

import pandas as pd
import pytest

import analysis

NAMES = {"G11": "승용차", "G14": "가구", "G31": "음식료품"}


def month_list(first_year, count):
    """first_year 1월부터 count개월의 연월(YYYYMM) 목록"""
    return [f"{first_year + i // 12}{i % 12 + 1:02d}" for i in range(count)]


def make_data(months, base_rates, sales_by_product, index_ids=("T3",)):
    """load_data()가 돌려주는 것과 같은 모양의 작은 표를 만든다."""
    rows = []
    for code, values in sales_by_product.items():
        for item in index_ids:
            for month, rate, value in zip(months, base_rates, values):
                rows.append({
                    "year_month": month, "C1": code, "C1_NM": NAMES[code], "ITM_ID": item,
                    "retail_index": value, "base_rate": rate, "collected_at": "2026-11-25",
                    "group": analysis.GROUP_BY_PREFIX[code[:2]],
                })
    return pd.DataFrame(rows)


@pytest.fixture
def three_years():
    """2015~2017년 36개월, 상품군 2개, 지수 2개짜리 데이터"""
    months = month_list(2015, 36)
    rates = [1.5] * 12 + [1.5, 1.5, 1.75, 1.75, 2.0, 2.0, 2.0, 1.75, 1.5, 1.5, 1.25, 1.25] + [1.25] * 12
    sales = {
        "G14": [100 + i + (i % 5) for i in range(36)],
        "G31": [100 + (i % 7) * 0.5 for i in range(36)],
    }
    return make_data(months, rates, sales, index_ids=("T2", "T3"))


# ---------- 숫자 변환 ----------

def test_clean_numbers_drops_rows_that_cannot_be_numbers():
    data = pd.DataFrame({
        "retail_index": ["101.5", "", "abc"],
        "base_rate": ["2.5", "2.5", "2.5"],
    })
    cleaned, dropped = analysis.clean_numbers(data)
    assert len(cleaned) == 1
    assert dropped == 2
    assert cleaned.loc[0, "retail_index"] == 101.5


# ---------- 전년동월비, 변화폭 ----------

def test_yoy_matches_completion_value():
    """요건정의서 완료 기준: 승용차 계절조정 2025.09 = (114.2 ÷ 108.4 − 1) × 100 = 5.35%"""
    data = make_data(["202409", "202509"], [3.5, 2.5], {"G11": [108.4, 114.2]})
    result = analysis.add_yoy(data).set_index("year_month")
    assert round(result.loc["202509", "sales_yoy"], 2) == 5.35
    assert math.isnan(result.loc["202409", "sales_yoy"])


def test_yoy_is_empty_when_last_year_month_is_missing():
    """1년 전 달이 없으면 다른 달과 잘못 짝짓지 않고 빈 값으로 둔다."""
    data = make_data(["202408", "202509"], [3.5, 2.5], {"G11": [100.0, 114.2]})
    result = analysis.add_yoy(data).set_index("year_month")
    assert math.isnan(result.loc["202509", "sales_yoy"])


def test_rate_change_matches_completion_value():
    """요건정의서 완료 기준: 2025.09 변화폭 = 2.50 − 3.50 = −1.00%p"""
    data = make_data(["202409", "202509"], [3.5, 2.5], {"G11": [108.4, 114.2]})
    rates = analysis.rate_table(data).set_index("year_month")
    assert rates.loc["202509", "rate_change"] == -1.0


def test_rate_table_stops_when_one_month_has_two_rates():
    data = make_data(["202409", "202409"], [3.5, 3.25], {"G11": [100.0, 101.0]})
    with pytest.raises(ValueError):
        analysis.rate_table(data)


def test_add_months_crosses_year():
    months = pd.Series(["202511", "202612"])
    assert analysis.add_months(months, 3).tolist() == ["202602", "202703"]
    assert analysis.add_months(pd.Series(["202601"]), 12).tolist() == ["202701"]


# ---------- 시차별 상관계수 ----------

def test_lag_correlation_toy_example():
    """판매가 2개월 늦게 반대로 움직이는 예시: k=0은 약 +0.43, k=2는 −1.00"""
    months = month_list(2016, 8)
    sales = pd.DataFrame({
        "year_month": months, "C1": "G11", "C1_NM": "승용차", "group": "내구재",
        "sales_yoy": [-2, -2, -1, -1, -2, -3, -3, -2],
    })
    rate_values = [1, 1, 2, 3, 3, 2, 1, 1]
    rates = pd.DataFrame({"year_month": months, "base_rate": rate_values, "rate_change": rate_values})

    lags = analysis.lag_correlations(sales, rates, max_lag=2, start="201601", end="201608")
    level = lags[lags["rate_type"] == "수준"].set_index("lag")

    assert round(level.loc[0, "corr"], 2) == 0.43
    assert round(level.loc[2, "corr"], 2) == -1.00
    # 짝 개수는 8 − k
    assert level["pairs"].tolist() == [8, 7, 6]


def test_lag_correlation_is_empty_when_too_few_pairs():
    months = month_list(2016, 2)
    sales = pd.DataFrame({
        "year_month": months, "C1": "G11", "C1_NM": "승용차", "group": "내구재", "sales_yoy": [1.0, 2.0],
    })
    rates = pd.DataFrame({"year_month": months, "base_rate": [1.0, 2.0], "rate_change": [0.0, 1.0]})
    lags = analysis.lag_correlations(sales, rates, max_lag=0, start="201601", end="201602")
    assert lags["corr"].isna().all()


# ---------- 민감도 순위 ----------

def test_ranking_orders_by_absolute_correlation():
    lags = pd.DataFrame([
        {"C1": "G14", "C1_NM": "가구", "group": "내구재", "rate_type": "변화폭", "lag": 0, "corr": 0.2, "pairs": 10},
        {"C1": "G14", "C1_NM": "가구", "group": "내구재", "rate_type": "변화폭", "lag": 1, "corr": -0.6, "pairs": 9},
        {"C1": "G31", "C1_NM": "음식료품", "group": "비내구재", "rate_type": "변화폭", "lag": 0, "corr": 0.3, "pairs": 10},
        {"C1": "G11", "C1_NM": "승용차", "group": "내구재", "rate_type": "변화폭", "lag": 0, "corr": float("nan"), "pairs": 2},
    ])
    ranking = analysis.sensitivity_ranking(lags)

    # −0.6이 +0.3보다 위, 대표 시차는 절댓값이 가장 큰 k=1, 빈 값인 승용차는 빠진다
    assert ranking["C1_NM"].tolist() == ["가구", "음식료품"]
    assert ranking.loc[0, "lag"] == 1
    assert ranking.loc[0, "corr"] == -0.6
    assert ranking["rank"].tolist() == [1, 2]


# ---------- 인상기·인하기 ----------

def test_hike_cut_average_excludes_flat_months():
    months = ["201601", "201602", "201603", "201604"]
    sales = pd.DataFrame({
        "year_month": months, "C1": "G11", "C1_NM": "승용차", "group": "내구재",
        "sales_yoy": [1.0, 3.0, -4.0, 10.0],
    })
    rates = pd.DataFrame({
        "year_month": months, "base_rate": [1.0] * 4, "rate_change": [0.25, 0.5, -0.25, 0.0],
    })
    result = analysis.hike_cut_average(sales, rates, "201601", "201604").iloc[0]

    assert result["hike_avg"] == 2.0      # (1 + 3) ÷ 2
    assert result["cut_avg"] == -4.0
    assert result["hike_months"] == 2
    assert result["cut_months"] == 1      # 변화폭 0인 201604(10.0)는 들어가지 않는다


# ---------- 요약 문장 ----------

def test_subject_particle():
    assert analysis.subject_particle("승용차") == "승용차가"
    assert analysis.subject_particle("음식료품") == "음식료품이"


def test_summary_when_no_result():
    empty = pd.DataFrame(columns=analysis.RANK_COLUMNS)
    assert "결과가 없습니다" in analysis.summary_text(empty)


# ---------- run_analysis: 입력 검사, 0건 ----------

def test_run_analysis_default(three_years):
    result = analysis.run_analysis(data=three_years)
    assert result["meta"]["start"] == "201601"
    assert result["meta"]["end"] == "201712"
    assert len(result["ranking"]) == 4          # 상품군 2개 × 수준·변화폭
    assert set(result["summary"]) == {"수준", "변화폭"}


@pytest.mark.parametrize("kwargs", [
    {"products": []},
    {"products": ["G99"]},
    {"start": "201712", "end": "201601"},
    {"start": "2016-01"},
    {"start": "201613"},
    {"start": "201501"},
    {"max_lag": 13},
    {"max_lag": -1},
    {"max_lag": True},
    {"index_type": "경상지수"},
])
def test_run_analysis_rejects_wrong_input(three_years, kwargs):
    with pytest.raises(ValueError):
        analysis.run_analysis(data=three_years, **kwargs)


def test_run_analysis_returns_message_when_no_result(three_years):
    """코로나 기간만 고르고 코로나 제외를 켜면 남는 달이 없다. 멈추지 않고 안내 문장을 준다."""
    months = month_list(2019, 36)
    data = three_years.assign(year_month=three_years["year_month"].map(dict(zip(month_list(2015, 36), months))))
    result = analysis.run_analysis(data=data, start="202003", end="202110", exclude_covid=True)
    assert result["ranking"].empty
    assert "결과가 없습니다" in result["summary"]["변화폭"]


# ---------- load_data: 샘플 대체 ----------

def test_load_data_uses_sample_when_real_file_missing(tmp_path, three_years):
    sample = tmp_path / "merged_sample.csv"
    three_years.to_csv(sample, index=False, encoding="utf-8-sig")

    data, info = analysis.load_data(merged_path=tmp_path / "없는파일.csv", sample_path=sample)
    assert info["source"] == "샘플 데이터"
    assert len(data) == len(three_years)


def test_load_data_stops_when_no_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        analysis.load_data(merged_path=tmp_path / "a.csv", sample_path=tmp_path / "b.csv")
