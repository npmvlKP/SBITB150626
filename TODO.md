# Phase 3 — Write All Tests (Instruction.8)

## Step 1: Repo understanding
- [x] Read `tests/conftest.py`
- [x] Read existing Phase 3 tests:
  - [x] `tests/unit/test_technical.py`
  - [x] `tests/unit/analysis/test_analysis_engine.py`
  - [x] `tests/unit/analysis/test_volume.py`
- [ ] Identify missing fixtures/tests vs Phase 3 requirements (8.1–8.7)

## Step 2: Add Phase 3 fixtures
- [ ] Update `tests/conftest.py` with Phase 3 fixtures:
  - [ ] `ta_settings`, `vol_settings`, `depth_settings`
  - [ ] `analysis_engine`
  - [ ] `sample_ohlcv_500`, `sample_ohlcv_100`
  - [ ] `sample_depth`
  - [ ] `sample_1min_bars`

## Step 3: Implement/expand unit tests
- [ ] Update `tests/unit/test_technical.py` with missing technical indicator tests (8.2)
- [ ] Update `tests/unit/analysis/test_volume.py` with missing volume tests (8.3)
- [ ] Update `tests/unit/analysis/test_depth.py` with missing depth tests (8.4)
- [ ] Update `tests/unit/analysis/test_analysis_engine.py` with missing integration tests (8.5)

## Step 4: Property tests
- [ ] Create/Update `tests/property/test_indicators.py` with 9 Hypothesis properties (8.6)

## Step 5: Benchmarks
- [ ] Create/Update `tests/bench/test_indicator_perf.py` with 5 pytest-benchmark tests (8.7)

## Step 6: Validation gates
- [ ] Run `pytest` (unit + property + integration)
- [ ] Run benchmark tests (if available)
- [ ] Run repo verification scripts if required by your gates:
  - [ ] `python verify_tests.py` (or relevant Phase 3 verifier)
  - [ ] Validate Windows 11 execution constraints
