from tradingagents.agents.utils.memory_log import TradingMemoryLog, memory_log_enabled


def test_trading_memory_log_append(tmp_path, monkeypatch):
    path = tmp_path / "mem.md"
    log = TradingMemoryLog(str(path))
    log.append_entry({"trade_date": "2026-05-23", "ticker": "600519.SH", "decision_md": "test"})
    assert path.exists()
    assert "600519.SH" in path.read_text(encoding="utf-8")


def test_memory_log_flag_default_off():
    assert memory_log_enabled({}) is False
    assert memory_log_enabled({"upgrade_persistent_memory": True}) is True
