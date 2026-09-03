from __future__ import annotations

import pandas as pd

from tradingagents.analytics.financial_health import build_financial_health_score
from tradingagents.analytics.intraday_features import (
    intraday_position_in_range,
    intraday_vwap_deviation,
    orderbook_imbalance,
)
from tradingagents.analytics.moneyflow_features import build_moneyflow_structure
from tradingagents.analytics.orderbook_proxy import (
    build_active_buy_proxy,
    build_orderbook_pressure_signal,
)


def test_intraday_features_basics():
    mins = pd.DataFrame(
        [
            {"close": 10.0, "vol": 100, "amount": 1000},
            {"close": 10.5, "vol": 200, "amount": 2100},
        ]
    )
    dev = intraday_vwap_deviation(mins, 10.6)
    assert dev is not None
    assert -0.2 < dev < 0.2
    assert intraday_position_in_range(11.0, 9.0, 10.0) == 0.5
    assert orderbook_imbalance({"ask_volume1": 100, "bid_volume1": 200}, level_count=1) > 0


def test_orderbook_and_active_buy_proxy():
    ob_dict, ob_text = build_orderbook_pressure_signal(
        {
            "ask_price1": 10.2,
            "ask_volume1": 1000,
            "bid_price1": 10.1,
            "bid_volume1": 500,
        },
        level_count=1,
    )
    assert ob_dict["method"] == "orderbook_pressure_signal_v1"
    assert "卖1档累计挂单" in ob_text

    mf = pd.DataFrame(
        [
            {
                "buy_lg_amount": 100.0,
                "sell_lg_amount": 80.0,
                "buy_elg_amount": 60.0,
                "sell_elg_amount": 20.0,
                "net_mf_amount": 50.0,
                "amount": 500.0,
            }
        ]
    )
    ab_dict, ab_text = build_active_buy_proxy(mf)
    assert ab_dict["method"] == "active_buy_proxy_v1"
    assert "近似指标，非真 L2 逐笔" in ab_text


def test_moneyflow_and_financial_health():
    mf = pd.DataFrame([{"net_mf_amount": 100.0}])
    ind = pd.DataFrame([{"rank": 2}, {"rank": 3}, {"rank": 4}])
    top = pd.DataFrame([{"net_buy": 200.0}])
    ms_dict, ms_text = build_moneyflow_structure(mf, ind, top)
    assert ms_dict["method"] == "moneyflow_structure_v1"
    assert "近5日主力净流入" in ms_text

    fi = pd.DataFrame([{"roe": 18.0, "n_income": 100.0}])
    income = pd.DataFrame([{"grossprofit_margin": 25.0}, {"grossprofit_margin": 27.0}])
    cashflow = pd.DataFrame([{"n_cashflow_act": 120.0}])
    bs = pd.DataFrame([{"debt_to_assets": 50.0}])
    fh_dict, fh_text = build_financial_health_score(fi, income, cashflow, bs, industry_code="食品饮料")
    assert fh_dict["method"] == "financial_health_v1"
    assert fh_dict["health_score"] >= 0
    assert "综合健康分" in fh_text
