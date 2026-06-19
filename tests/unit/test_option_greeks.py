"""
Unit tests for Greeks Computation Engine (Phase 2).

Covers:
- OptionMetricsComputer.compute_single()
- RiskFreeRateProvider.get_rate() with T-Bill and Futures Basis methods
- QuantLibCalendar trading day functions
- Error handling for deep OTM/ITM options

Uses Hypothesis for property-based testing.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from config.settings import GreeksSettings

# Import the module under test
from src.data.option_chain import (
    OptionMetrics,
    OptionMetricsComputer,
    QuantLibCalendar,
    RiskFreeRateProvider,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def greeks_settings() -> GreeksSettings:
    """Default Greeks settings for testing."""
    return GreeksSettings(
        RFR_METHOD="t_bill",
        RFR_T_BILL_DEFAULT=0.065,
        RFR_T_BILL_FETCH_URL="https://www.rbi.org.in/scripts/BS_NSDPDisplay.aspx",
        RFR_FUTURES_SYMBOL="NIFTY",
        MIN_TTM_DAYS=1,
        MIN_OPTION_PRICE=0.05,
        IV_MAX_ITERATIONS=100,
        IV_PRECISION=1e-6,
        IV_UPPER_BOUND=5.0,
        IV_LOWER_BOUND=0.001,
    )


@pytest.fixture
def mock_rfr_provider(greeks_settings) -> MagicMock:
    """Mock RFR provider returning a fixed rate."""
    mock = MagicMock(spec=RiskFreeRateProvider)
    mock.get_rate = AsyncMock(return_value=0.065)
    return mock


@pytest.fixture
def mock_db_url() -> str:
    """Mock database URL."""
    return "postgresql://test:test@localhost:5432/test_db"


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = MagicMock()
    mock.ping.return_value = True
    mock.get.return_value = None
    mock.setex.return_value = True
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# OptionMetricsComputer Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestOptionMetricsComputer:
    """Tests for OptionMetricsComputer class."""

    def test_compute_single_atm_call(self, greeks_settings, mock_rfr_provider):
        """ATM CE with known inputs should compute valid Greeks."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        spot = 21500.0
        strike = 21500.0
        expiry_date = date(2024, 1, 25)
        as_of_date = date(2024, 1, 15)
        option_ltp = 350.0
        option_type: Literal["CE", "PE"] = "CE"
        rfr = 0.065

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        result = computer.compute_single(
            spot=spot,
            strike=strike,
            expiry_date=expiry_date,
            as_of_date=as_of_date,
            option_ltp=option_ltp,
            option_type=option_type,
            risk_free_rate=rfr,
        )

        assert result.compute_error is None, f"Computation failed: {result.compute_error}"
        assert result.iv is not None
        assert result.iv > 0, f"IV should be positive, got {result.iv}"
        assert result.iv <= greeks_settings.IV_UPPER_BOUND
        assert result.delta is not None
        assert 0.3 < result.delta < 0.7, f"ATM call delta should be ~0.50, got {result.delta}"
        assert result.gamma is not None
        assert result.gamma > 0, f"Gamma should be positive, got {result.gamma}"
        assert result.vega is not None
        assert result.vega > 0, f"Vega should be positive, got {result.vega}"
        assert result.theta is not None
        assert result.theta < 0, f"Long call theta should be negative, got {result.theta}"

    def test_compute_single_atm_put(self, greeks_settings, mock_rfr_provider):
        """ATM PE with known inputs should compute valid Greeks."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=320.0,
            option_type="PE",
            risk_free_rate=0.065,
        )

        assert result.compute_error is None
        assert result.iv is not None
        assert result.iv > 0
        assert result.delta is not None
        assert -0.7 < result.delta < -0.3, f"ATM put delta should be ~-0.50, got {result.delta}"
        assert result.theta is not None
        assert result.theta < 0

    def test_compute_single_expired(self, greeks_settings, mock_rfr_provider):
        """Expired option (expiry <= as_of_date) should return error."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 10),  # Before as_of_date
            as_of_date=date(2024, 1, 15),
            option_ltp=350.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result.compute_error == "expired"
        assert result.ttm_years == 0.0
        assert result.iv is None
        assert result.delta is None

    def test_compute_single_zero_price(self, greeks_settings, mock_rfr_provider):
        """Option with price below MIN_OPTION_PRICE threshold should return error."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=0.01,  # Below MIN_OPTION_PRICE of 0.05
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result.compute_error == "price_below_threshold"
        assert result.iv is None
        assert result.delta is None

    def test_compute_single_negative_price(self, greeks_settings, mock_rfr_provider):
        """Option with negative price should return error."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=-10.0,  # Invalid negative price
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result.compute_error is not None

    def test_compute_single_deep_otm(self, greeks_settings, mock_rfr_provider):
        """Deep OTM option may fail IV computation - this is expected."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=22500.0,  # 1000 points OTM
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=50.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        # Either succeeds or fails - both are acceptable
        if result.compute_error is None:
            assert result.delta is not None
            assert abs(result.delta) < 0.2

    def test_compute_single_itm(self, greeks_settings, mock_rfr_provider):
        """Deep ITM option may fail IV computation - this is expected."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=20500.0,  # 1000 points ITM
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=1100.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        # Either succeeds or fails - both are acceptable
        if result.compute_error is None and result.delta is not None:
            assert result.delta > 0.7

    def test_ttm_minimum_enforced(self, greeks_settings, mock_rfr_provider):
        """TTM should be at least MIN_TTM_DAYS, even for same-day expiry."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        as_of_date = date(2024, 1, 24)
        expiry_date = date(2024, 1, 25)  # 1 day to expiry
        expected_ttm = greeks_settings.MIN_TTM_DAYS / 365.0

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=expiry_date,
            as_of_date=as_of_date,
            option_ltp=200.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result.ttm_years == pytest.approx(expected_ttm, rel=0.01)

    def test_rfr_passed_through(self, greeks_settings, mock_rfr_provider):
        """Risk-free rate should be passed through to result."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=350.0,
            option_type="CE",
            risk_free_rate=0.0725,
        )

        assert result.risk_free_rate == 0.0725

    def test_async_wrapper_works(self, greeks_settings, mock_rfr_provider):
        """compute_single_async should return same result as compute_single."""
        import asyncio

        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        result_async = asyncio.run(
            computer.compute_single_async(
                spot=21500.0,
                strike=21500.0,
                expiry_date=date(2024, 1, 25),
                as_of_date=date(2024, 1, 15),
                option_ltp=350.0,
                option_type="CE",
                risk_free_rate=0.065,
            )
        )

        result_sync = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=350.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result_async.iv == result_sync.iv
        assert result_async.delta == result_sync.delta
        assert result_async.compute_error == result_sync.compute_error

    def test_vollib_not_available_graceful(self, greeks_settings, mock_rfr_provider):
        """Should handle missing vollib gracefully."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)
        computer._vollib_available = False

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date(2024, 1, 25),
            as_of_date=date(2024, 1, 15),
            option_ltp=350.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result.compute_error == "vollib_not_available"
        assert result.iv is None


# ─────────────────────────────────────────────────────────────────────────────
# RiskFreeRateProvider Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRiskFreeRateProvider:
    """Tests for RiskFreeRateProvider class."""

    def test_rbi_parse_success(self, greeks_settings, mock_db_url):
        """Should parse RBI page for T-bill yield."""
        provider = RiskFreeRateProvider(greeks_settings, mock_db_url)

        html = """
        <table>
        <tr><td>91-Day T-Bill</td><td>6.55</td></tr>
        <tr><td>182-Day T-Bill</td><td>6.72</td></tr>
        </table>
        """

        rate = provider._parse_rbi_t_bill_yield(html)

        assert rate is not None
        assert rate == pytest.approx(0.0655, rel=0.01)

    def test_rbi_parse_no_data(self, greeks_settings, mock_db_url):
        """Should return None when RBI page has no T-bill data."""
        provider = RiskFreeRateProvider(greeks_settings, mock_db_url)

        html = "<html><body>No yield data available</body></html>"

        rate = provider._parse_rbi_t_bill_yield(html)

        assert rate is None

    @pytest.mark.asyncio
    async def test_get_rate_fallback_default(self, greeks_settings, mock_db_url):
        """Should fall back to default when fetch fails."""
        provider = RiskFreeRateProvider(greeks_settings, mock_db_url)

        # No Redis, httpx will fail - should fallback to default
        rate = await provider.get_rate(date(2024, 1, 15))

        # Should return default since network fetch will fail
        assert rate == greeks_settings.RFR_T_BILL_DEFAULT

    @pytest.mark.asyncio
    async def test_get_rate_returns_float(self, greeks_settings, mock_db_url):
        """Should return a valid float rate."""
        provider = RiskFreeRateProvider(greeks_settings, mock_db_url)

        rate = await provider.get_rate(date(2024, 1, 15))

        assert isinstance(rate, float)
        assert 0.0 < rate < 0.2  # Reasonable range


# ─────────────────────────────────────────────────────────────────────────────
# QuantLibCalendar Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQuantLibCalendar:
    """Tests for QuantLibCalendar class."""

    def test_calendar_generates_trading_days(self):
        """Should generate trading days for date range."""
        calendar = QuantLibCalendar.get_trading_calendar(2024, 2024)

        assert len(calendar) > 0
        assert len(calendar) < 366

        for d in calendar:
            assert d.weekday() < 5, f"{d} is a weekend"

    def test_calendar_cached(self):
        """Same year range should return cached result."""
        QuantLibCalendar._calendar_cache.clear()

        cal1 = QuantLibCalendar.get_trading_calendar(2024, 2024)
        cal2 = QuantLibCalendar.get_trading_calendar(2024, 2024)

        assert cal1 is cal2

    def test_is_trading_day_weekend(self):
        """Weekend should not be a trading day."""
        saturday = date(2024, 1, 13)
        assert not QuantLibCalendar.is_trading_day(saturday)

        sunday = date(2024, 1, 14)
        assert not QuantLibCalendar.is_trading_day(sunday)

    def test_get_next_trading_day(self):
        """Should return next weekday after weekend."""
        friday = date(2024, 1, 12)

        next_day = QuantLibCalendar.get_next_trading_day(friday)

        assert next_day.weekday() == 0  # Monday

    def test_get_previous_trading_day(self):
        """Should return previous weekday before weekend."""
        monday = date(2024, 1, 15)

        prev_day = QuantLibCalendar.get_previous_trading_day(monday)

        assert prev_day.weekday() == 4  # Friday


# ─────────────────────────────────────────────────────────────────────────────
# Property-Based Tests (Hypothesis)
# ─────────────────────────────────────────────────────────────────────────────


class TestGreeksInvariants:
    """Property-based tests for Greek invariants using Hypothesis."""

    @given(
        spot=st.floats(min_value=5000, max_value=25000),
        strike=st.floats(min_value=5000, max_value=25000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_delta_call_bounds(self, spot, strike):
        """CE delta should be in [0, 1] if computed."""
        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        mock_provider.get_rate = AsyncMock(return_value=0.065)

        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("c", spot, strike, 30 / 365, 0.065, 0.2)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=0.065,
            )

            if result.delta is not None:
                assert 0 <= result.delta <= 1, f"CE delta should be in [0,1], got {result.delta}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=100, max_value=50000),
        strike=st.floats(min_value=100, max_value=50000),
    )
    @settings(max_examples=50)
    def test_delta_put_bounds(self, spot, strike):
        """PE delta should be in [-1, 0] if computed."""
        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        mock_provider.get_rate = AsyncMock(return_value=0.065)

        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("p", spot, strike, 30 / 365, 0.065, 0.2)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="PE",
                risk_free_rate=0.065,
            )

            if result.delta is not None:
                assert -1 <= result.delta <= 0, f"PE delta should be in [-1,0], got {result.delta}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=5000, max_value=25000),
        strike=st.floats(min_value=5000, max_value=25000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_gamma_non_negative(self, spot, strike):
        """Gamma should be >= 0 if computed."""
        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        mock_provider.get_rate = AsyncMock(return_value=0.065)

        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not available")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("c", spot, strike, 30 / 365, 0.065, 0.2)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=0.065,
            )

            if result.gamma is not None:
                assert result.gamma >= 0, f"Gamma should be non-negative, got {result.gamma}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=5000, max_value=25000),
        strike=st.floats(min_value=5000, max_value=25000),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_vega_non_negative(self, spot, strike):
        """Vega should be >= 0 if computed."""
        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        mock_provider.get_rate = AsyncMock(return_value=0.065)

        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not available")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("c", spot, strike, 30 / 365, 0.065, 0.2)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=0.065,
            )

            if result.vega is not None:
                assert result.vega >= 0, f"Vega should be non-negative, got {result.vega}"

        except ImportError:
            pytest.skip("py_vollib not available")


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_invalid_inputs_never_crash(self, greeks_settings, mock_rfr_provider):
        """Invalid inputs should never raise exceptions - always return error."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        invalid_cases = [
            (0, 100, 10, "zero_spot"),
            (100, 0, 10, "zero_strike"),
            (100, 100, 0, "zero_price"),
            (100, 100, -10, "negative_price"),
            (float("inf"), 100, 10, "infinite_spot"),
            (100, float("nan"), 10, "nan_strike"),
        ]

        for spot, strike, ltp, desc in invalid_cases:
            try:
                result = computer.compute_single(
                    spot=spot,
                    strike=strike,
                    expiry_date=date(2024, 1, 25),
                    as_of_date=date(2024, 1, 15),
                    option_ltp=ltp,
                    option_type="CE",
                    risk_free_rate=0.065,
                )
                assert result is not None
                assert isinstance(result, OptionMetrics)
            except Exception as e:
                pytest.fail(f"Case {desc} raised exception: {e}")

    def test_very_short_expiry(self, greeks_settings, mock_rfr_provider):
        """Very short expiry should still work with MIN_TTM_DAYS enforced."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date.today(),
            as_of_date=date.today(),
            option_ltp=100.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result is not None
        assert isinstance(result, OptionMetrics)
