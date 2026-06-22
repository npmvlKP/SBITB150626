# Phase 2 Verification Report -- SBITB-150626

**Timestamp:** 2026-06-22T13:01:40.976687
**Root:** G:\OC\SBITB-150626
**Python:** 3.12.7 (tags/v3.12.7:0b05ead, Oct  1 2024, 03:06:41) [MSC v.1941 64 bit (AMD64)]
**Platform:** win32

## Tier 0 -- Every PR Gate

| Gate | Command | Status | Duration |
|------|---------|--------|----------|
| mypy --strict | `mypy src/ --strict` | PASS | 2.6s |
| ruff check | `ruff check src/ tests/` | PASS | 0.1s |
| ruff format --check | `ruff format --check src/ tests/` | PASS | 0.1s |
| bandit (no HIGH) | `"C:\Program Files\Python312\python.exe" -m bandit ` | PASS | 1.8s |
| unit tests + coverage >=80% | `"C:\Program Files\Python312\python.exe" -m pytest ` | PASS | 43.3s |
| pip-audit (requirements.txt) | `"C:\Program Files\Python312\python.exe" -m pip_aud` | PASS | 72.5s |
| gitleaks (no secrets) | `gitleaks detect --source .` | PASS | 35.5s |

## Tier 1 -- Extended

| Gate | Command | Status | Duration |
|------|---------|--------|----------|
| property tests (Hypothesis) | `"C:\Program Files\Python312\python.exe" -m pytest ` | PASS | 15.6s |
| benchmarks (<10ms single) | `"C:\Program Files\Python312\python.exe" -m pytest ` | PASS | 34.4s |
| integration tests | `"C:\Program Files\Python312\python.exe" -m pytest ` | SKIP | 0.0s |
| Kleppmann Ch.1-5 validation | `python verify_phase2_kleppmann.py` | PASS | 0.2s |

## Tier 2 -- Security

| Gate | Command | Status | Duration |
|------|---------|--------|----------|
| pip-audit detailed | `"C:\Program Files\Python312\python.exe" -m pip_aud` | PASS | 67.7s |
| SBOM generation | `cyclonedx-bom -o sbom.json` | SKIP | 0.0s |
| trivy filesystem scan | `trivy fs .` | PASS | 3.5s |

## Summary

- **Passed:** 12
- **Failed:** 0
- **Skipped:** 2

**PHASE 2 GATE: PASS**
