"""Main OpenAlgo NIFTY Options Strategy engine.

Integrates technical indicators + OpenAlgo SDK for live trading.
Runs as an isolated subprocess spawned by the OpenAlgo platform.

Signal Logic (Chan Ch.5-6 + Kaufman Ch.9-10):
  TRENDING regime  → Options BUYING (momentum, delta 0.50-0.60)
  MEAN_REVERTING   → Options SELLING (strangle, 2SD, premium decay)
  RANDOM_WALK/UNKNOWN → No new positions (capital preservation)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import numpy.typing as npt

from openalgo_strategy.config import StrategyConfig, get_config
from openalgo_strategy.indicators import (
    compute_adx,
    compute_atr,
    compute_bbands,
    compute_ema_pair,
    compute_macd,
    compute_rsi,
    compute_supertrend,
    detect_regime,
)


class StrategyEngine:
    """Core strategy engine — fetches data, computes signals, places orders via OpenAlgo."""

    def __init__(
        self,
        config: StrategyConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or get_config()
        self._client = client
        self._signal_count_today = 0
        self._current_date: str | None = None
        self._last_signal_ts: datetime | None = None

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def client(self) -> Any:
        """Lazily initialize OpenAlgo API client from environment."""
        if self._client is None:
            from openalgo import api

            api_key = os.environ.get("OPENALGO_API_KEY", "")
            host = os.environ.get("OPENALGO_HOST", "http://127.0.0.1:5000")
            if not api_key:
                raise RuntimeError("OPENALGO_API_KEY environment variable not set")
            self._client = api(api_key=api_key, host=host)
        return self._client

    # ── Data fetching ───────────────────────────────────────────────────

    def fetch_candles(self, symbol: str | None = None) -> npt.NDArray[np.float64]:
        """Fetch historical OHLCV candles via OpenAlgo history API.

        Returns numpy array with columns [open, high, low, close, volume].
        """
        sym = symbol or self.config.underlying
        resp = self.client.history(
            symbol=sym,
            interval=self.config.candle_interval,
            bars=self.config.lookback_bars,
        )
        return self._parse_history_response(resp)

    def _parse_history_response(self, resp: Any) -> npt.NDArray[np.float64]:
        """Parse OpenAlgo history response into OHLCV numpy array.

        Handles both dict-with-data and DataFrame responses.
        """
        data: Any = None
        if isinstance(resp, dict):
            data = resp.get("data", resp)
        else:
            data = resp

        # Fast path: empty payload → empty (0,5) array (no pandas needed)
        if data is None or (hasattr(data, "__len__") and len(data) == 0):
            return np.empty((0, 5), dtype=np.float64)

        try:
            import pandas as pd  # noqa: PLC0415

            if isinstance(data, pd.DataFrame):
                df = data
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame(data)
        except ImportError:
            return self._parse_history_fallback(data)

        # After DataFrame construction, re-check for emptiness (e.g., [] rows)
        if df.empty:
            return np.empty((0, 5), dtype=np.float64)

        col_map = {c.lower().strip(): c for c in df.columns}
        open_col = self._find_col(col_map, ["open"])
        high_col = self._find_col(col_map, ["high"])
        low_col = self._find_col(col_map, ["low"])
        close_col = self._find_col(col_map, ["close", "ltp"])
        vol_col = self._find_col(col_map, ["volume", "vol"])

        if not all([open_col, high_col, low_col, close_col]):
            raise ValueError(f"Cannot find OHLC columns in: {list(df.columns)}")

        vol_data = df[vol_col].values if vol_col else np.zeros(len(df))
        ohlcv = np.column_stack(
            [
                df[open_col].astype(float).values,
                df[high_col].astype(float).values,
                df[low_col].astype(float).values,
                df[close_col].astype(float).values,
                np.asarray(vol_data, dtype=float),
            ]
        )
        return ohlcv

    @staticmethod
    def _find_col(col_map: dict[str, str], candidates: list[str]) -> str | None:
        for c in candidates:
            if c in col_map:
                return col_map[c]
        return None

    @staticmethod
    def _parse_history_fallback(data: Any) -> npt.NDArray[np.float64]:
        """Fallback parser if pandas is unavailable (should not happen in OpenAlgo)."""
        if not isinstance(data, list) or len(data) == 0:
            return np.empty((0, 5), dtype=np.float64)
        first = data[0]
        if isinstance(first, dict):
            rows = [
                [
                    float(r.get("open", r.get("o", 0))),
                    float(r.get("high", r.get("h", 0))),
                    float(r.get("low", r.get("l", 0))),
                    float(r.get("close", r.get("c", r.get("ltp", 0)))),
                    float(r.get("volume", r.get("v", 0))),
                ]
                for r in data
            ]
            return np.array(rows, dtype=np.float64)
        return np.array(data, dtype=np.float64)

    # ── Technical analysis ──────────────────────────────────────────────

    def compute_indicators(self, ohlcv: npt.NDArray[np.float64]) -> dict[str, Any]:
        """Compute all technical indicators from OHLCV data."""
        if len(ohlcv) < 30:
            return {"regime": "UNKNOWN", "bars": len(ohlcv)}

        h = ohlcv[:, 1].astype(np.float64)
        low = ohlcv[:, 2].astype(np.float64)
        c = ohlcv[:, 3].astype(np.float64)

        rsi = compute_rsi(c, self.config.rsi_period)
        macd_line, macd_signal, _ = compute_macd(
            c, self.config.macd_fast, self.config.macd_slow, self.config.macd_signal
        )
        adx = compute_adx(h, low, c, self.config.adx_period)
        atr = compute_atr(h, low, c, self.config.atr_period)
        bb_u, bb_m, bb_l = compute_bbands(c, self.config.bbands_period, self.config.bbands_stddev)
        ema_f, ema_s, ema_signal = compute_ema_pair(c, self.config.ema_fast, self.config.ema_slow)
        st_val, st_dir = compute_supertrend(h, low, c)
        regime = detect_regime(c, adx, self.config.adx_trending_threshold)

        return {
            "rsi": rsi,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "adx": adx,
            "atr": atr,
            "bbands_upper": bb_u,
            "bbands_middle": bb_m,
            "bbands_lower": bb_l,
            "ema_fast": ema_f,
            "ema_slow": ema_s,
            "ema_signal": ema_signal,
            "supertrend_value": st_val,
            "supertrend_direction": st_dir,
            "regime": regime,
            "timestamp": datetime.now(UTC),
        }

    # ── Signal generation ───────────────────────────────────────────────

    def generate_signal(self, indicators: dict[str, Any]) -> dict[str, Any]:
        """Generate trading signal from indicators.

        Returns dict with keys: action (BUY/SELL/HOLD), reason, regime.
        """
        regime = indicators.get("regime", "UNKNOWN")
        if regime in ("UNKNOWN", "RANDOM_WALK"):
            return {"action": "HOLD", "reason": f"Regime={regime}, no edge", "regime": regime}

        rsi = indicators.get("rsi")
        ema_signal = indicators.get("ema_signal")
        adx = indicators.get("adx")
        st_dir = indicators.get("supertrend_direction")

        if regime == "TRENDING":
            return self._generate_buying_signal(rsi, ema_signal, adx, st_dir, regime)
        return self._generate_selling_signal(rsi, adx, regime)

    def _generate_buying_signal(
        self,
        rsi: float | None,
        ema_signal: int | None,
        adx: float | None,
        st_dir: int | None,
        regime: str,
    ) -> dict[str, Any]:
        """Options buying signal (momentum, Chan Ch.6)."""
        if adx is not None and adx < self.config.buying_adx_min:
            return {"action": "HOLD", "reason": f"ADX {adx:.1f} < min {self.config.buying_adx_min}", "regime": regime}
        if ema_signal == 1 and st_dir == 1 and rsi is not None and rsi < 70:
            return {"action": "BUY_CE", "reason": "Bullish momentum: EMA cross + Supertrend + RSI<70", "regime": regime}
        if ema_signal == -1 and st_dir == -1 and rsi is not None and rsi > 30:
            return {"action": "BUY_PE", "reason": "Bearish momentum: EMA cross + Supertrend + RSI>30", "regime": regime}
        return {"action": "HOLD", "reason": "No momentum confirmation", "regime": regime}

    def _generate_selling_signal(
        self,
        rsi: float | None,
        adx: float | None,
        regime: str,
    ) -> dict[str, Any]:
        """Options selling signal (mean-reversion, Chan Ch.5)."""
        if adx is not None and adx > self.config.selling_adx_max:
            return {"action": "HOLD", "reason": f"ADX {adx:.1f} > max {self.config.selling_adx_max}", "regime": regime}
        if rsi is not None and rsi > 70:
            return {"action": "SELL_STRANGLE", "reason": "Overbought: RSI>70, sell premium", "regime": regime}
        if rsi is not None and rsi < 30:
            return {"action": "SELL_STRANGLE", "reason": "Oversold: RSI<30, sell premium", "regime": regime}
        return {"action": "HOLD", "reason": "No mean-reversion edge", "regime": regime}

    # ── Position sizing ─────────────────────────────────────────────────

    def compute_position_size(self, capital: Decimal, premium: Decimal) -> int:
        """Compute lot count using fixed-fractional risk (Kaufman Ch.9).

        Args:
            capital: Total available capital.
            premium: Option premium per share.

        Returns:
            Number of lots (capped at max_lots_per_trade).
        """
        if premium <= 0:
            return 0
        risk_amount = capital * self.config.fixed_fractional_pct
        cost_per_lot = premium * Decimal(self.config.nifty_lot_size)
        if cost_per_lot <= 0:
            return 0
        lots = int(risk_amount / cost_per_lot)
        return min(max(lots, 0), self.config.max_lots_per_trade)

    # ── SEBI compliance checks ──────────────────────────────────────────

    def check_rate_limit(self) -> bool:
        """Verify ≤3 OPS self-imposed limit (NSE/INVG/67858 threshold is 10)."""
        now = datetime.now(UTC)
        if self._last_signal_ts is not None:
            elapsed = (now - self._last_signal_ts).total_seconds()
            if elapsed < 1.0 / self.config.sebi_max_ops:
                return False
        self._last_signal_ts = now
        return True

    def check_daily_signal_limit(self) -> bool:
        """Reset daily counter and verify ≤ max_daily_signals."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._current_date != today:
            self._current_date = today
            self._signal_count_today = 0
        return self._signal_count_today < self.config.max_daily_signals

    def validate_order_value(self, premium: Decimal, lots: int) -> bool:
        """Verify order value ≤ Rs 2,00,000 (CIR/MRD/DP/09/2012)."""
        order_value = premium * Decimal(self.config.nifty_lot_size) * Decimal(lots)
        return order_value <= self.config.max_order_value

    # ── Order placement ─────────────────────────────────────────────────

    def execute_signal(
        self,
        signal: dict[str, Any],
        symbol: str,
        premium: Decimal,
        capital: Decimal,
    ) -> dict[str, Any]:
        """Execute a trading signal via OpenAlgo place_order API.

        Returns order response dict or skip reason.
        """
        action = signal.get("action", "HOLD")
        if action == "HOLD":
            return {"status": "SKIPPED", "reason": signal.get("reason", "HOLD")}

        if not self.check_rate_limit():
            return {"status": "REJECTED", "reason": "Rate limit: ≤3 OPS"}
        if not self.check_daily_signal_limit():
            return {"status": "REJECTED", "reason": "Daily signal limit reached"}

        lots = self.compute_position_size(capital, premium)
        if lots == 0:
            return {"status": "SKIPPED", "reason": "Insufficient capital for 1 lot"}

        if not self.validate_order_value(premium, lots):
            return {"status": "REJECTED", "reason": f"Order value > {self.config.max_order_value}"}

        side = "BUY" if action.startswith("BUY") else "SELL"
        self._signal_count_today += 1

        resp = self.client.place_order(
            symbol=symbol,
            exchange=self.config.exchange,
            segment=self.config.segment,
            transaction_type=side,
            variety="regular",
            quantity=lots * self.config.nifty_lot_size,
            product=self.config.product,
            price="MARKET",
            order_type="MKT",
        )
        return {"status": "PLACED", "response": resp, "lots": lots, "action": action}

    # ── Main loop ───────────────────────────────────────────────────────

    def run_once(self) -> dict[str, Any]:
        """Single evaluation cycle: fetch → analyze → signal → (optionally) execute.

        Returns the full decision context for logging/audit.
        """
        ohlcv = self.fetch_candles()
        indicators = self.compute_indicators(ohlcv)
        signal = self.generate_signal(indicators)
        result: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "strategy_id": self.config.strategy_id,
            "indicators": indicators,
            "signal": signal,
        }
        if signal["action"] != "HOLD":
            result["execution"] = {"status": "DRY_RUN", "reason": "No symbol/premium provided to execute_once"}
        return result


def main() -> None:
    """Entry point for OpenAlgo subprocess execution."""
    engine = StrategyEngine()
    result = engine.run_once()
    print(f"[{result['timestamp']}] {result['strategy_id']}: {result['signal']}")


if __name__ == "__main__":
    main()
