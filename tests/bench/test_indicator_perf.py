"""Volume Profile Algorithm Benchmark"""

import numpy as np
import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from config.settings import VolumeProfileSettings
from src.analysis.volume import VolumeProfileComputer


@pytest.fixture(scope="module")
def volume_profiler():
    """Fixture for VolumeProfile computation."""
    return VolumeProfileSettings()


@pytest.fixture(scope="module")
def test_pricing_data():
    """Create test price series with realistic volume metrics."""
    realized_price_open = np.array([20000.0, 20200.0], dtype=np.float64)
    high = np.array([20500.0, 20700.0], dtype=np.float64)
    low_prices = np.array([19500.0, 19600.0], dtype=np.float64)
    close = np.array([20200.0, 20300.0], dtype=np.float64)
    volume = np.array([100000.0, 110000.0], dtype=np.float64)
    return np.column_stack((realized_price_open, high, low_prices, close, volume))


def test_volume_profile_operation(
    benchmark: BenchmarkFixture, volume_profiler: VolumeProfileSettings, test_pricing_data: np.ndarray
) -> None:
    """Benchmark volume profile computation function."""
    open_prices, high, low, close_prices, volume = test_pricing_data.T
    cpu = VolumeProfileComputer(volume_profiler)

    def benchmark_report():
        cpu.compute(high=high, low=low, close=close_prices, volume=volume)

    benchmark(benchmark_report)
