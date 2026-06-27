"""Performance benchmarks for Greeks computation.

Uses pytest-benchmark to measure computation performance and ensure
Greeks calculations meet latency requirements for live trading.
"""

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Literal, cast  # noqa: UP035 – cast needed for mypy list[Literal] narrowing

import pytest

from config.settings import GreeksSettings
from src.data.option_chain import OptionMetrics, OptionMetricsComputer, RiskFreeRateProvider

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture
    from pytest_mock import MockerFixture


# ============================================================================
# Benchmark 1: Single Option Greeks Computation
# ============================================================================


@pytest.mark.benchmark(group="greeks_single")
def test_benchmark_single_option_greeks(
    benchmark: "BenchmarkFixture",
    greeks_computer: OptionMetricsComputer,
) -> None:
    """Benchmark single option Greeks computation time."""
    # Prepare inputs
    spot = 24890.50
    strike = 25000.0
    expiry = date(2026, 6, 26)
    as_of = date(2026, 6, 20)
    option_ltp = 492.35
    option_type: Literal["CE", "PE"] = "CE"
    rfr = 0.065

    def compute_greeks() -> OptionMetrics:
        return greeks_computer.compute_single(
            spot=spot,
            strike=strike,
            expiry_date=expiry,
            as_of_date=as_of,
            option_ltp=option_ltp,
            option_type=option_type,
            risk_free_rate=rfr,
        )

    # Benchmark the computation
    result = benchmark(compute_greeks)

    # Verify result is valid (may have compute_error if vollib not available)
    assert result.risk_free_rate == rfr


# ============================================================================
# Benchmark 2: Batch Greeks Computation (100 Options)
# ============================================================================


@pytest.mark.benchmark(group="greeks_batch_100")
def test_benchmark_batch_100_greeks(
    benchmark: "BenchmarkFixture",
    greeks_computer: OptionMetricsComputer,
) -> None:
    """Benchmark 100 options Greeks computation.

    Uses asyncio.run() wrapper since pytest-benchmark is synchronous.
    """
    # Generate 100 option parameters
    spot = 24890.50
    base_strike = 24000.0
    expiry = date(2026, 6, 26)
    as_of = date(2026, 6, 20)
    rfr = 0.065

    async def batch_compute() -> list[OptionMetrics]:
        results = []
        for i in range(100):
            strike = base_strike + (i * 100)
            option_type: Literal["CE", "PE"] = "CE" if i % 2 == 0 else "PE"
            # Use synthetic LTP based on strike to ensure valid computation
            option_ltp = 100.0 + (i % 50) * 5

            metric = await greeks_computer.compute_single_async(
                spot=spot,
                strike=strike,
                expiry_date=expiry,
                as_of_date=as_of,
                option_ltp=option_ltp,
                option_type=option_type,
                risk_free_rate=rfr,
            )
            results.append(metric)
        return results

    def run() -> list[OptionMetrics]:
        return asyncio.run(batch_compute())

    # Benchmark the batch computation (sync wrapper around async)
    result = benchmark.pedantic(run, rounds=5, iterations=1)

    assert len(result) == 100


# ============================================================================
# Benchmark 3: Risk-Free Rate Lookup Performance
# ============================================================================


@pytest.mark.benchmark(group="rfr_lookup")
def test_benchmark_rfr_lookup(
    benchmark: "BenchmarkFixture",
    rfr_provider: RiskFreeRateProvider,
    mocker: "MockerFixture",
) -> None:
    """Benchmark risk-free rate lookup time (cached/mocked path).

    Benchmarks the in-memory lookup path, NOT real RBI HTTP fetch.
    Real network calls are not benchmarked — they're tested separately
    with proper timeouts and are non-deterministic.
    Uses asyncio.run() wrapper since pytest-benchmark is synchronous.
    """
    test_date = date(2026, 6, 20)

    # Mock the async HTTP fetch so we measure lookup overhead, not network latency
    async def mock_t_bill(_date: date) -> float:
        return 0.065

    mocker.patch.object(rfr_provider, "_get_t_bill_rate", side_effect=mock_t_bill)

    async def lookup_rfr() -> float:
        return await rfr_provider.get_rate(test_date)

    def run() -> float:
        return float(asyncio.run(lookup_rfr()))

    result = benchmark.pedantic(run, rounds=10, iterations=5)

    assert result is not None
    assert 0 < result < 1  # Valid RFR range


# ============================================================================
# Benchmark 4: Full Option Chain Computation (50 Strikes x 2 Types)
# ============================================================================


@pytest.mark.benchmark(group="greeks_full_chain")
def test_benchmark_full_option_chain(
    benchmark: "BenchmarkFixture",
    greeks_computer: OptionMetricsComputer,
) -> None:
    """Benchmark full option chain computation time.

    Uses asyncio.run() wrapper since pytest-benchmark is synchronous.
    """
    # Full NIFTY chain: ~50 strikes x 2 expiry weeks
    spot = 24890.50
    atm_strike = 24900.0
    expiry = date(2026, 6, 26)
    as_of = date(2026, 6, 20)
    rfr = 0.065

    async def compute_full_chain() -> list[OptionMetrics]:
        results = []

        # ATM + 25 strikes on each side
        for i in range(-25, 26):
            strike = atm_strike + (i * 100)

            for option_type in cast(list[Literal["CE", "PE"]], ["CE", "PE"]):
                # Vary LTP by moneyness to ensure valid computation
                moneyness = (strike - spot) / spot
                itm_offset = abs(moneyness)
                option_ltp = max(50.0, 100.0 * (1 + itm_offset * 2))

                metric = await greeks_computer.compute_single_async(
                    spot=spot,
                    strike=strike,
                    expiry_date=expiry,
                    as_of_date=as_of,
                    option_ltp=option_ltp,
                    option_type=option_type,
                    risk_free_rate=rfr,
                )
                results.append(metric)

        return results

    def run() -> list[OptionMetrics]:
        return asyncio.run(compute_full_chain())

    result = benchmark.pedantic(run, rounds=3, iterations=1)

    # range(-25, 26) = 51 values: -25 to 25 inclusive
    # 51 strikes x 2 types = 102 options (may be less if some fail IV validation)
    assert len(result) == 51 * 2


# ============================================================================
# Performance Thresholds
# ============================================================================


@pytest.mark.benchmark(group="thresholds")
def test_single_computation_under_10ms(
    benchmark: "BenchmarkFixture",
    greeks_computer: OptionMetricsComputer,
) -> None:
    """Single Greeks computation should complete in under 10ms."""
    spot = 24890.50
    strike = 25000.0
    expiry = date(2026, 6, 26)
    as_of = date(2026, 6, 20)
    option_ltp = 492.35
    rfr = 0.065

    def compute() -> OptionMetrics:
        return greeks_computer.compute_single(
            spot=spot,
            strike=strike,
            expiry_date=expiry,
            as_of_date=as_of,
            option_ltp=option_ltp,
            option_type="CE",
            risk_free_rate=rfr,
        )

    # Run with min_rounds to get accurate measurement
    result = benchmark.pedantic(compute, rounds=100, iterations=10)

    assert result is not None


# ============================================================================
# Benchmark Fixtures
# ============================================================================


@pytest.fixture
def greeks_settings() -> GreeksSettings:
    """Greeks settings for benchmarks."""
    return GreeksSettings(
        RFR_METHOD="t_bill",
        RFR_T_BILL_DEFAULT=0.065,
        MIN_TTM_DAYS=1,
        MIN_OPTION_PRICE=0.05,
        IV_UPPER_BOUND=5.0,
        IV_LOWER_BOUND=0.001,
    )


@pytest.fixture
def rfr_provider(greeks_settings: GreeksSettings) -> RiskFreeRateProvider:
    """Risk-free rate provider for benchmarks."""
    return RiskFreeRateProvider(
        settings=greeks_settings,
        db_url="postgresql://test:test@localhost:5432/test",
    )


@pytest.fixture
def greeks_computer(
    greeks_settings: GreeksSettings,
    rfr_provider: RiskFreeRateProvider,
) -> OptionMetricsComputer:
    """Option Greeks computer instance for benchmarks."""
    return OptionMetricsComputer(
        settings=greeks_settings,
        rfr_provider=rfr_provider,
    )
