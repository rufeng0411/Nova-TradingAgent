"""Alpha158 + TA extra factors handler (T7 comparison baseline).

Extends official Alpha158. TA columns (stk_factor_pro / moneyflow / daily_basic)
are exported to CSV via ``export_tushare_to_qlib --include-ta-factors``; full bin
registration is deferred. This handler keeps Alpha158 features identical so
``workflow_lightgbm_alpha158_ta_extra.yaml`` can run side-by-side with the pure
Alpha158 workflow; IC uplift is measured separately in ``run_t7_ta_factors.py``.
"""

from __future__ import annotations

from qlib.contrib.data.handler import Alpha158


class Alpha158TaExtra(Alpha158):
    """Alpha158 baseline with TA-extra hook for future custom bin fields."""

    def __init__(self, *args, use_ta_extra: bool = False, **kwargs):
        self.use_ta_extra = use_ta_extra
        super().__init__(*args, **kwargs)
