from unittest.mock import patch
import pytest

from tradingagents.graph.data_collector import (
    DataCollector,
    _parse_csv_to_dataframe,
    _stock_data_parse_issue,
    make_cache_key,
)


def test_make_cache_key():
    assert make_cache_key("600519", "2026-03-12") == "600519_2026-03-12"


def test_parse_csv_to_dataframe_accepts_mixed_case_english_columns():
    raw = """# header
Date,Open,High,Low,Close,Volume
2026-03-10,10,12,9,11,1000
2026-03-11,11,13,10,12,1200
"""
    df = _parse_csv_to_dataframe(raw)
    assert df is not None
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df.iloc[-1]["close"] == pytest.approx(12)


def test_parse_csv_to_dataframe_accepts_chinese_ohlcv_columns():
    raw = """日期,开盘,最高,最低,收盘,成交量
2026-03-10,10,12,9,11,1000
2026-03-11,11,13,10,12,1200
"""
    df = _parse_csv_to_dataframe(raw)
    assert df is not None
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df.iloc[0]["volume"] == pytest.approx(1000)


def test_stock_data_parse_issue_reports_missing_normalized_columns():
    raw = "日期,开盘,收盘\n2026-03-10,10,11\n2026-03-11,11,12\n"
    df = _parse_csv_to_dataframe(raw)
    assert df is None
    issue = _stock_data_parse_issue(raw)
    assert "stock_data" in issue


def test_collect_populates_required_keys():
    collector = DataCollector()
    stub_pool = {
        "stock_data": "data", "indicators": {}, "news": "n", "global_news": "gn",
        "fundamentals": "f", "balance_sheet": "bs", "cashflow": "cf",
        "income_statement": "is", "fund_flow_board": "ffb",
        "fund_flow_individual": "ffi", "lhb": "lhb",
        "insider_transactions": "it", "zt_pool": "zt", "hot_stocks": "hs",
    }
    with patch("tradingagents.graph.data_collector._fetch_all", return_value=stub_pool):
        result = collector.collect("600519", "2026-03-12")
    assert "stock_data" in result
    assert "lhb" in result
    assert "zt_pool" in result


def test_collect_uses_cache_on_second_call():
    collector = DataCollector()
    stub_pool = {"stock_data": "x", "indicators": {}}
    with patch("tradingagents.graph.data_collector._fetch_all", return_value=stub_pool) as mock_fetch:
        collector.collect("600519", "2026-03-12")
        collector.collect("600519", "2026-03-12")
    assert mock_fetch.call_count == 1


def test_evict_removes_from_cache():
    collector = DataCollector()
    collector._cache["600519_2026-03-12"] = {"stock_data": "x"}
    collector.evict("600519", "2026-03-12")
    assert "600519_2026-03-12" not in collector._cache


def test_get_window_short_returns_14_day_window():
    collector = DataCollector()
    pool = {"stock_data": "x", "indicators": {}}
    sliced = collector.get_window(pool, horizon="short", trade_date="2026-03-12")
    assert sliced["_data_window"] == "14天"
    assert sliced["_horizon"] == "short"


def test_get_window_medium_returns_90_day_window():
    collector = DataCollector()
    pool = {"stock_data": "x", "indicators": {}}
    sliced = collector.get_window(pool, horizon="medium", trade_date="2026-03-12")
    assert sliced["_data_window"] == "90天"
    assert sliced["_horizon"] == "medium"
