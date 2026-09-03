from scheduler.jobs import marketdata_loop as ml


def test_new_sync_functions_exist():
    assert callable(ml._sync_daily_basic)
    assert callable(ml._sync_limit_list)
    assert callable(ml._sync_moneyflow_market)
    assert callable(ml._sync_margin_detail)
    assert callable(ml._sync_hsgt_top10)
    assert callable(ml._sync_top_list_and_inst)
    assert callable(ml._sync_stk_factor_pro_market)
    assert callable(ml._sync_cyq_perf_market)
    assert callable(ml._sync_fina_indicator_forecast_express)
    assert callable(ml._sync_holdernumber)
