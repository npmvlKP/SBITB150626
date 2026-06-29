"""Tests for OpenAlgo strategy package — indicators, config, engine.

All external APIs (OpenAlgo SDK) are mocked. No real broker calls.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from openalgo_strategy.config import StrategyConfig, get_config
from openalgo_strategy.engine import StrategyEngine
from openalgo_strategy.indicators import (
    compute_adx,
    compute_atr,
    compute_bbands,
    compute_ema_pair,
    compute_hurst,
    compute_macd,
    compute_rsi,
    compute_supertrend,
    detect_regime,
)

# ═══════════════════════════════════════════════════════════════════════
# Config tests
# ═══════════════════════════════════════════════════════════════════════


class TestStrategyConfig:
    def test_default_config(self) -> None:
        cfg = StrategyConfig()
        assert cfg.underlying == "NSE:NIFTY"
        assert cfg.nifty_lot_size == 25
        assert cfg.fixed_fractional_pct == Decimal("0.02")
        assert cfg.sebi_max_ops == 3

    def test_config_immutable(self) -> None:
        cfg = StrategyConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.underlying = "NSE:BANKNIFTY"  # type: ignore[misc]

    def test_get_config_from_env(self) -> None:
        with patch.dict("os.environ", {"STRATEGY_ID": "test_123"}):
            cfg = get_config()
            assert cfg.strategy_id == "test_123"

    def test_max_order_value_sebi_compliant(self) -> None:
        cfg = StrategyConfig()
        assert cfg.max_order_value == Decimal("200000")


# ═══════════════════════════════════════════════════════════════════════
# Indicator tests
# ═══════════════════════════════════════════════════════════════════════


class TestRSI:
    def test_insufficient_data_returns_none(self) -> None:
        close = np.array([100.0, 101.0, 102.0])
        assert compute_rsi(close, period=14) is None

    def test_all_gains_rsi_100(self) -> None:
        close = np.linspace(100.0, 130.0, 30)
        rsi = compute_rsi(close, period=14)
        assert rsi is not None
        assert rsi > 90  # Strongly trending up

    def test_all_losses_rsi_near_0(self) -> None:
        close = np.linspace(130.0, 100.0, 30)
        rsi = compute_rsi(close, period=14)
        assert rsi is not None
        assert rsi < 10

    def test_flat_rsi_50_or_100(self) -> None:
        close = np.full(30, 100.0)
        rsi = compute_rsi(close, period=14)
        assert rsi is not None
        # No losses → RSI = 100
        assert rsi == 100.0


class TestMACD:
    def test_insufficient_data(self) -> None:
        close = np.array([100.0, 101.0])
        line, signal, hist = compute_macd(close)
        assert line is None
        assert signal is None
        assert hist is None

    def test_uptrend_macd_positive(self) -> None:
        # Exponential growth → accelerating momentum → MACD line > signal
        close = np.exp(np.linspace(0, 0.4, 60)) * 100
        line, signal, _ = compute_macd(close)
        assert line is not None
        assert signal is not None
        assert line > signal  # Bullish

    def test_downtrend_macd_negative(self) -> None:
        close = np.linspace(150.0, 100.0, 60)
        line, signal, _ = compute_macd(close)
        assert line is not None
        assert line < signal  # Bearish


class TestADX:
    def test_insufficient_data(self) -> None:
        close = np.array([100.0, 101.0, 102.0])
        high = np.array([101.0, 102.0, 103.0])
        low = np.array([99.0, 100.0, 101.0])
        assert compute_adx(high, low, close, period=14) is None

    def test_strong_trend_high_adx(self) -> None:
        close = np.linspace(100.0, 160.0, 50)
        high = close + 2.0
        low = close - 2.0
        adx = compute_adx(high, low, close, period=14)
        assert adx is not None
        assert adx > 20


class TestATR:
    def test_insufficient_data(self) -> None:
        close = np.array([100.0])
        assert compute_atr(close, close, close, period=14) is None

    def test_atr_positive(self) -> None:
        np.random.seed(42)
        close = np.cumsum(np.random.randn(30)) + 100
        high = close + np.abs(np.random.randn(30)) + 1
        low = close - np.abs(np.random.randn(30)) - 1
        atr = compute_atr(high, low, close, period=14)
        assert atr is not None
        assert atr > 0


class TestBollingerBands:
    def test_insufficient_data(self) -> None:
        close = np.array([100.0, 101.0])
        u, m, lo = compute_bbands(close, period=20)
        assert u is None

    def test_band_ordering(self) -> None:
        close = np.random.randn(40) + 100
        u, m, lo = compute_bbands(close, period=20)
        assert u is not None
        assert m is not None
        assert lo is not None
        assert u > m > lo


class TestEMA:
    def test_crossover_signal(self) -> None:
        close = np.linspace(100.0, 150.0, 50)
        f, s, signal = compute_ema_pair(close, fast=9, slow=21)
        assert signal == 1  # Bullish

    def test_bearish_signal(self) -> None:
        close = np.linspace(150.0, 100.0, 50)
        f, s, signal = compute_ema_pair(close, fast=9, slow=21)
        assert signal == -1


class TestSupertrend:
    def test_insufficient_data(self) -> None:
        close = np.array([100.0, 101.0])
        assert compute_supertrend(close, close, close) == (None, None)

    def test_returns_direction(self) -> None:
        close = np.linspace(100.0, 140.0, 30)
        high = close + 2
        low = close - 2
        val, direction = compute_supertrend(high, low, close)
        assert val is not None
        assert direction in (1, -1)


class TestHurst:
    def test_insufficient_data(self) -> None:
        close = np.array([100.0] * 50)
        assert compute_hurst(close) is None

    def test_trending_series(self) -> None:
        close = np.exp(np.linspace(0, 0.001 * 200, 200))
        h = compute_hurst(close)
        assert h is not None


class TestRegime:
    def test_unknown_when_no_adx(self) -> None:
        close = np.linspace(100.0, 120.0, 200)
        assert detect_regime(close, None) == "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════
# Engine tests
# ═══════════════════════════════════════════════════════════════════════


class TestStrategyEnginePositionSizing:
    def _engine(self) -> StrategyEngine:
        cfg = StrategyConfig()
        return StrategyEngine(config=cfg, client=MagicMock())

    def test_zero_premium_returns_zero(self) -> None:
        engine = self._engine()
        assert engine.compute_position_size(Decimal("100000"), Decimal("0")) == 0

    def test_normal_sizing(self) -> None:
        engine = self._engine()
        # capital=100000, risk=2%=2000, premium=40, lot=25 → cost/lot=1000
        # lots = 2000/1000 = 2
        lots = engine.compute_position_size(Decimal("100000"), Decimal("40"))
        assert lots == 2

    def test_capped_at_max(self) -> None:
        engine = self._engine()
        lots = engine.compute_position_size(Decimal("10000000"), Decimal("10"))
        assert lots == engine.config.max_lots_per_trade

    def test_insufficient_capital(self) -> None:
        engine = self._engine()
        lots = engine.compute_position_size(Decimal("100"), Decimal("500"))
        assert lots == 0


class TestStrategyEngineCompliance:
    def _engine(self) -> StrategyEngine:
        return StrategyEngine(config=StrategyConfig(), client=MagicMock())

    def test_order_value_under_limit(self) -> None:
        engine = self._engine()
        # 40 * 25 * 2 = 2000 ≤ 200000
        assert engine.validate_order_value(Decimal("40"), 2) is True

    def test_order_value_over_limit(self) -> None:
        engine = self._engine()
        # 500 * 25 * 10 = 125000... try higher: 1000 * 25 * 10 = 250000 > 200000
        assert engine.validate_order_value(Decimal("1000"), 10) is False

    def test_rate_limit_blocks_rapid_calls(self) -> None:
        engine = self._engine()
        assert engine.check_rate_limit() is True
        assert engine.check_rate_limit() is False  # Too fast

    def test_daily_signal_limit(self) -> None:
        engine = self._engine()
        # Prime the date tracker so the counter isn't reset by the check
        engine.check_daily_signal_limit()
        for _ in range(engine.config.max_daily_signals):
            engine._signal_count_today += 1
        assert engine.check_daily_signal_limit() is False


class TestStrategyEngineSignals:
    def _engine(self) -> StrategyEngine:
        return StrategyEngine(config=StrategyConfig(), client=MagicMock())

    def test_hold_on_unknown_regime(self) -> None:
        engine = self._engine()
        sig = engine.generate_signal({"regime": "UNKNOWN"})
        assert sig["action"] == "HOLD"

    def test_hold_on_random_walk(self) -> None:
        engine = self._engine()
        sig = engine.generate_signal({"regime": "RANDOM_WALK"})
        assert sig["action"] == "HOLD"

    def test_buy_ce_on_trending_bullish(self) -> None:
        engine = self._engine()
        sig = engine.generate_signal(
            {
                "regime": "TRENDING",
                "adx": 30.0,
                "ema_signal": 1,
                "supertrend_direction": 1,
                "rsi": 55.0,
            }
        )
        assert sig["action"] == "BUY_CE"

    def test_buy_pe_on_trending_bearish(self) -> None:
        engine = self._engine()
        sig = engine.generate_signal(
            {
                "regime": "TRENDING",
                "adx": 30.0,
                "ema_signal": -1,
                "supertrend_direction": -1,
                "rsi": 45.0,
            }
        )
        assert sig["action"] == "BUY_PE"

    def test_sell_strangle_overbought(self) -> None:
        engine = self._engine()
        sig = engine.generate_signal(
            {
                "regime": "MEAN_REVERTING",
                "adx": 15.0,
                "rsi": 75.0,
            }
        )
        assert sig["action"] == "SELL_STRANGLE"


class TestStrategyEngineExecute:
    def _engine(self) -> StrategyEngine:
        mock_client = MagicMock()
        mock_client.place_order.return_value = {"status": "success", "order_id": "12345"}
        return StrategyEngine(config=StrategyConfig(), client=mock_client)

    def test_hold_skipped(self) -> None:
        engine = self._engine()
        result = engine.execute_signal(
            {"action": "HOLD", "reason": "test"},
            symbol="NIFTY",
            premium=Decimal("100"),
            capital=Decimal("100000"),
        )
        assert result["status"] == "SKIPPED"

    def test_buy_executed(self) -> None:
        engine = self._engine()
        result = engine.execute_signal(
            {"action": "BUY_CE", "reason": "momentum"},
            symbol="NIFTY24DECCALL",
            premium=Decimal("40"),
            capital=Decimal("100000"),
        )
        assert result["status"] == "PLACED"
        assert result["lots"] >= 1


class TestStrategyEngineParseHistory:
    def _engine(self) -> StrategyEngine:
        return StrategyEngine(config=StrategyConfig(), client=MagicMock())

    def test_parse_dict_response(self) -> None:
        engine = self._engine()
        resp = {
            "data": [
                {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
                {"open": 101, "high": 103, "low": 100, "close": 102, "volume": 1500},
            ]
        }
        ohlcv = engine._parse_history_response(resp)
        assert ohlcv.shape == (2, 5)
        assert ohlcv[0, 0] == 100.0  # open
        assert ohlcv[1, 4] == 1500.0  # volume

    def test_parse_list_response(self) -> None:
        engine = self._engine()
        resp = [
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        ]
        ohlcv = engine._parse_history_response(resp)
        assert ohlcv.shape == (1, 5)

    def test_parse_empty_response(self) -> None:
        engine = self._engine()
        ohlcv = engine._parse_history_response({"data": []})
        assert len(ohlcv) == 0


class TestStrategyEngineIndicators:
    def _engine(self) -> StrategyEngine:
        return StrategyEngine(config=StrategyConfig(), client=MagicMock())

    def test_insufficient_bars(self) -> None:
        engine = self._engine()
        ohlcv = np.array([[100, 101, 99, 100, 1000]], dtype=np.float64)
        result = engine.compute_indicators(ohlcv)
        assert result["regime"] == "UNKNOWN"

    def test_full_indicators(self) -> None:
        engine = self._engine()
        np.random.seed(42)
        n = 250
        close = np.cumsum(np.random.randn(n) * 0.5) + 100
        high = close + np.abs(np.random.randn(n)) + 1
        low = close - np.abs(np.random.randn(n)) - 1
        volume = np.random.randint(1000, 5000, n).astype(float)
        ohlcv = np.column_stack([close, high, low, close, volume])
        result = engine.compute_indicators(ohlcv)
        assert "regime" in result
        assert "rsi" in result
        assert "adx" in result
