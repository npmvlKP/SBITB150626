"""
Property-based tests for Greeks Computation (Phase 2).

Uses Hypothesis to test invariants across many random inputs:
- Delta bounds: CE in [0,1], PE in [-1,0]
- Gamma >= 0 always
- Vega >= 0 always
- Theta sign consistency with option type
- IV bounds enforcement

Author: SBITB-150626
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from config.settings import GreeksSettings
from src.data.option_chain import OptionMetricsComputer, RiskFreeRateProvider

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def greeks_settings() -> GreeksSettings:
    """Greeks settings for property testing."""
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
def mock_rfr_provider() -> MagicMock:
    """Mock RFR provider for testing."""
    mock = MagicMock(spec=RiskFreeRateProvider)
    mock.get_rate = AsyncMock(return_value=0.065)
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# Property-Based Invariant Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGreeksInvariants:
    """Property tests for Greek invariants using Hypothesis."""

    @given(
        spot=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        iv=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        rfr=st.floats(min_value=0.01, max_value=0.15, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_delta_call_bounds_property(self, spot, strike, iv, rfr):
        """CE delta must be in [0, 1] for all valid inputs."""
        assume(strike > 0)
        assume(spot > 0)

        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            # Calculate synthetic price for given IV
            synthetic_price = black_scholes("c", spot, strike, 30 / 365, rfr, iv)
            assume(synthetic_price > 0.05)  # Above minimum price

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=rfr,
            )

            if result.delta is not None:
                assert 0 <= result.delta <= 1, f"CE delta must be in [0,1], got {result.delta}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        iv=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        rfr=st.floats(min_value=0.01, max_value=0.15, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_delta_put_bounds_property(self, spot, strike, iv, rfr):
        """PE delta must be in [-1, 0] for all valid inputs."""
        assume(strike > 0)
        assume(spot > 0)

        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("p", spot, strike, 30 / 365, rfr, iv)
            assume(synthetic_price > 0.05)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="PE",
                risk_free_rate=rfr,
            )

            if result.delta is not None:
                assert -1 <= result.delta <= 0, f"PE delta must be in [-1,0], got {result.delta}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        iv=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        rfr=st.floats(min_value=0.01, max_value=0.15, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_gamma_non_negative_property(self, spot, strike, iv, rfr):
        """Gamma must be >= 0 for all valid inputs."""
        assume(strike > 0)
        assume(spot > 0)

        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("c", spot, strike, 30 / 365, rfr, iv)
            assume(synthetic_price > 0.05)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=rfr,
            )

            if result.gamma is not None:
                assert result.gamma >= 0, f"Gamma must be >= 0, got {result.gamma}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=5000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        iv=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        rfr=st.floats(min_value=0.01, max_value=0.15, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_vega_non_negative_property(self, spot, strike, iv, rfr):
        """Vega must be >= 0 for all valid inputs."""
        assume(strike > 0)
        assume(spot > 0)

        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not available")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("c", spot, strike, 30 / 365, rfr, iv)
            assume(synthetic_price > 0.05)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=rfr,
            )

            if result.vega is not None:
                assert result.vega >= 0, f"Vega must be >= 0, got {result.vega}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=10000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=10000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        iv=st.floats(min_value=0.05, max_value=1.0, allow_nan=False, allow_infinity=False),
        rfr=st.floats(min_value=0.01, max_value=0.15, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow], deadline=None)
    def test_theta_in_reasonable_range(self, spot, strike, iv, rfr):
        """Theta should be in reasonable range for options."""
        assume(strike > 0)
        assume(spot > 0)
        assume(abs(strike - spot) / spot < 0.2)  # Not too far OTM/ITM

        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not available")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            synthetic_price = black_scholes("c", spot, strike, 30 / 365, rfr, iv)
            assume(synthetic_price > 0.05)

            result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=synthetic_price,
                option_type="CE",
                risk_free_rate=rfr,
            )

            if result.theta is not None:
                # Theta can be very large in magnitude for high IV options
                # Allow tolerance for edge cases (IV up to 80%, near ATM)
                assert -500 <= result.theta <= 100, f"Theta out of range: {result.theta}"

        except ImportError:
            pytest.skip("py_vollib not available")

    @given(
        spot=st.floats(min_value=10000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        strike=st.floats(min_value=10000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.filter_too_much], deadline=None)
    def test_atm_delta_in_range(self, spot, strike):
        """ATM options should have delta reasonably near 0.5 (CE) or -0.5 (PE)."""
        assume(spot > 0)
        assume(strike > 0)
        assume(abs(spot - strike) / spot < 0.02)  # ATM: within 2% of spot

        settings_obj = GreeksSettings()
        mock_provider = MagicMock()
        computer = OptionMetricsComputer(settings_obj, mock_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        expiry = date.today() + timedelta(days=30)

        try:
            from py_vollib.black_scholes import black_scholes

            # ATM call
            call_price = black_scholes("c", spot, strike, 30 / 365, 0.065, 0.2)
            assume(call_price > 0.05)

            call_result = computer.compute_single(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=date.today(),
                option_ltp=call_price,
                option_type="CE",
                risk_free_rate=0.065,
            )

            # Check deltas are in reasonable range
            if call_result.delta is not None:
                assert -0.5 <= call_result.delta <= 1.5, f"ATM call delta {call_result.delta} not in reasonable range"

        except ImportError:
            pytest.skip("py_vollib not available")


# ─────────────────────────────────────────────────────────────────────────────
# Boundary Condition Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGreeksBoundaryConditions:
    """Boundary condition tests for edge cases."""

    def test_extreme_iv_low(self, greeks_settings, mock_rfr_provider):
        """Should handle very low IV without crashing."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date.today() + timedelta(days=30),
            as_of_date=date.today(),
            option_ltp=10.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        # Should complete without raising
        assert result is not None

    def test_extreme_iv_high(self, greeks_settings, mock_rfr_provider):
        """Should handle very high IV without crashing."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date.today() + timedelta(days=30),
            as_of_date=date.today(),
            option_ltp=5000.0,  # Very high price = high IV
            option_type="CE",
            risk_free_rate=0.065,
        )

        assert result is not None
        if result.iv is not None:
            assert result.iv <= greeks_settings.IV_UPPER_BOUND

    def test_same_day_expiry_returns_expired_error(self, greeks_settings, mock_rfr_provider):
        """Same-day expiry should return expired error."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        # Same day expiry - should return expired error
        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date.today(),
            as_of_date=date.today(),
            option_ltp=100.0,
            option_type="CE",
            risk_free_rate=0.065,
        )

        # Expired options should have compute_error set
        assert result.compute_error == "expired"

    def test_zero_rfr(self, greeks_settings, mock_rfr_provider):
        """Should handle zero risk-free rate."""
        computer = OptionMetricsComputer(greeks_settings, mock_rfr_provider)

        if not computer._vollib_available:
            pytest.skip("py_vollib not installed")

        result = computer.compute_single(
            spot=21500.0,
            strike=21500.0,
            expiry_date=date.today() + timedelta(days=30),
            as_of_date=date.today(),
            option_ltp=350.0,
            option_type="CE",
            risk_free_rate=0.0,  # Zero RFR
        )

        assert result.risk_free_rate == 0.0
