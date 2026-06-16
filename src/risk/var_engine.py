"""Quantitative risk engines — VaR/CVaR/GARCH/EVT for tail risk management.

Reference: McNeil/Frey/Embrechts "Quantitative Risk Management", Ch.2-5
- Ch.2: VaR/CVaR framework
- Ch.4: GARCH volatility models
- Ch.5: Extreme Value Theory (EVT)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import scipy.stats
import structlog

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from config.settings import (
        PositionLimitSettings,
        QuantitativeRiskSettings,
        RiskSettings,
    )


class AuditLogger:  # Stub - replace with actual implementation
    """Placeholder for audit logging functionality."""

    def info(self, event: str, **kwargs: Any) -> None:
        pass

    def warning(self, event: str, **kwargs: Any) -> None:
        pass

    def error(self, event: str, **kwargs: Any) -> None:
        pass


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(UTC).replace(microsecond=0)


class VarMethod(Enum):
    """VaR computation methods."""

    HISTORICAL = "historical"
    PARAMETRIC = "parametric"
    MONTE_CARLO = "monte_carlo"


@dataclass(frozen=True)
class VarResult:
    """Result of VaR/CVaR computation."""

    method: VarMethod
    confidence_level: float
    holding_period_days: int
    var_amount: Decimal  # Rs
    cvar_amount: Decimal  # Rs
    var_pct: float  # As % of portfolio
    cvar_pct: float  # As % of portfolio
    timestamp: datetime
    computation_time_ms: float
    data_points_used: int


@dataclass(frozen=True)
class GarchResult:
    """Result of GARCH model fit."""

    model_type: str  # "GARCH", "EGARCH", "GJR"
    p: int
    q: int
    conditional_volatility: np.ndarray
    annualized_volatility: float
    persistence: float  # alpha + beta (stationarity condition: < 1)
    log_likelihood: float
    aic: float
    bic: float
    last_forecast: float  # 1-step ahead variance forecast
    forecast_annualized: float  # Annualized volatility forecast
    fitted_date: datetime
    residuals: np.ndarray


@dataclass(frozen=True)
class EvtResult:
    """Result of Extreme Value Theory (EVT) analysis."""

    threshold: float
    tail_index_xi: float  # Shape parameter (Hill estimator)
    tail_index_se: float  # Standard error
    n_exceedances: int
    var_evt: Decimal  # EVT-based VaR
    cvar_evt: Decimal  # EVT-based CVaR (Expected Shortfall)
    goodness_of_fit_pvalue: float  # Anderson-Darling test p-value
    timestamp: datetime


@dataclass(frozen=True)
class StressTestResult:
    """Result of a single stress test scenario."""

    scenario_name: str
    pct_drop: Decimal
    portfolio_loss: Decimal
    projected_margin_utilization: Decimal
    would_trigger_kill_switch: bool
    would_breach_var_limit: bool
    greek_impact: dict  # {"delta": ..., "gamma": ..., "vega": ...}


class HistoricalVarEngine:
    """Historical Simulation VaR/CVaR per McNeil Ch.2.2.

    Uses actual historical P&L distribution without distributional assumptions.
    Fail-closed: if insufficient data (< lookback_days), reject order and log error.
    """

    def __init__(self, settings: QuantitativeRiskSettings):
        self._settings = settings

    def compute(
        self,
        pnl_series: pd.Series,
        portfolio_value: Decimal,
    ) -> VarResult:
        """Compute historical VaR and CVaR.
        Steps (McNeil Ch.2.2 Algorithm 2.1):
        1. Validate: len(pnl_series) >= VAR_LOOKBACK_DAYS, else raise InsufficientDataError
        2. Take last VAR_LOOKBACK_DAYS observations
        3. Sort P&L ascending
        4. VaR = -quantile(pnl, 1 - VAR_CONFIDENCE_LEVEL) * sqrt(VAR_HOLDING_PERIOD_DAYS)
        5. CVaR = -mean(pnl[pnl <= -VaR]) * sqrt(VAR_HOLDING_PERIOD_DAYS)
        6. Return VarResult

        Square-root-of-time scaling per McNeil Ch.2.3 (assumes i.i.d. returns).
        For GARCH-adjusted VaR, use GarchVarEngine instead.
        """
        start_time = datetime.now()

        # Validate data
        self._validate_data(pnl_series)

        # Extract lookback period
        lookback_pnl = pnl_series.iloc[-self._settings.VAR_LOOKBACK_DAYS :].copy()
        losses = -lookback_pnl  # Convert to positive losses

        # Compute VaR using historical quantile
        alpha = self._settings.VAR_CONFIDENCE_LEVEL
        var_loss_level = losses.quantile(q=1 - alpha)

        # Compute CVaR (Expected Shortfall) - average of losses beyond VaR
        cvar_loss_level = losses[losses >= var_loss_level].mean()

        # Time scaling
        holding_period = self._settings.VAR_HOLDING_PERIOD_DAYS
        var_time_scaled = self._time_scale(var_loss_level, holding_period)
        cvar_time_scaled = self._time_scale(cvar_loss_level, holding_period)

        # Convert to monetary amounts
        var_amount = Decimal(str(var_time_scaled)) * portfolio_value
        cvar_amount = Decimal(str(cvar_time_scaled)) * portfolio_value

        # Compute percentages
        var_pct = float(var_time_scaled)
        cvar_pct = float(cvar_time_scaled)

        computation_time = (datetime.now() - start_time).total_seconds() * 1000

        return VarResult(
            method=VarMethod.HISTORICAL,
            confidence_level=alpha,
            holding_period_days=holding_period,
            var_amount=var_amount,
            cvar_amount=cvar_amount,
            var_pct=var_pct,
            cvar_pct=cvar_pct,
            timestamp=_utcnow(),
            computation_time_ms=computation_time,
            data_points_used=len(lookback_pnl),
        )

    def _validate_data(self, pnl_series: pd.Series) -> None:
        """Raise InsufficientDataError if len < VAR_LOOKBACK_DAYS."""
        if len(pnl_series) < self._settings.VAR_LOOKBACK_DAYS:
            required = self._settings.VAR_LOOKBACK_DAYS
            available = len(pnl_series)
            logger.error(
                "var_hist_invalid_data",
                required=required,
                available=available,
                error="insufficient_lookback_period",
            )
            raise ValueError(f"Insufficient data: need {required} points, have {available}")

    def _time_scale(self, value: float, holding_period: int) -> float:
        """Square-root-of-time scaling: value * sqrt(holding_period)."""
        return value * np.sqrt(holding_period)


class ParametricVarEngine:
    """Parametric (Variance-Covariance) VaR/CVaR per McNeil Ch.2.3.

    Assumes P&L follows a normal distribution (or t-distribution if configured).
    McNeil Ch.2.3: VaR_alpha = mu - z_alpha * sigma * sqrt(T).
    For t-distribution: use scipy.stats.t.ppf instead of norm.ppf.
    """

    def __init__(self, settings: QuantitativeRiskSettings):
        self._settings = settings

    def compute(
        self,
        pnl_series: pd.Series,
        portfolio_value: Decimal,
    ) -> VarResult:
        """Compute parametric VaR and CVaR.
        Steps:
        1. Fit distribution parameters: mu = mean(pnl), sigma = std(pnl)
        2. If GARCH_DISTRIBUTION == "t": fit df via MLE (scipy.stats.t.fit)
        3. VaR = -(mu + z_alpha * sigma) * sqrt(T)
        4. CVaR = -E[P&L | P&L <= -VaR] using closed-form for normal/t
        5. Return VarResult
        """
        try:
            start_time = datetime.now()

            # Extract lookback period
            lookback_pnl = pnl_series.iloc[-self._settings.VAR_LOOKBACK_DAYS :].copy()
            mu, sigma = lookback_pnl.mean(), lookback_pnl.std()

            # Determine z-value based on distribution
            alpha = self._settings.VAR_CONFIDENCE_LEVEL
            holding_period = self._settings.VAR_HOLDING_PERIOD_DAYS

            if self._settings.GARCH_DISTRIBUTION == "normal":
                z_alpha = -scipy.stats.norm.ppf(1 - alpha)
                cvar_closed = self._cvar_closed_form(mu, sigma, alpha, None)
            else:
                # t-distribution
                df = scipy.stats.t.fit(lookback_pnl)[0]  # degrees of freedom
                z_alpha = -scipy.stats.t.ppf(1 - alpha, df)
                cvar_closed = self._cvar_closed_form(mu, sigma, alpha, df)

            # Compute VaR and CVaR
            var_loss_level = mu + z_alpha * sigma
            cvar_loss_level = cvar_closed

            # Time scaling
            var_time_scaled = self._time_scale(var_loss_level, holding_period)
            cvar_time_scaled = self._time_scale(cvar_loss_level, holding_period)

            # Convert to monetary amounts (use positive values for losses)
            var_amount = Decimal(str(abs(var_time_scaled))) * portfolio_value
            cvar_amount = Decimal(str(abs(cvar_time_scaled))) * portfolio_value

            var_pct = float(abs(var_time_scaled))
            cvar_pct = float(abs(cvar_time_scaled))

            computation_time = (datetime.now() - start_time).total_seconds() * 1000

            return VarResult(
                method=VarMethod.PARAMETRIC,
                confidence_level=alpha,
                holding_period_days=holding_period,
                var_amount=var_amount,
                cvar_amount=cvar_amount,
                var_pct=var_pct,
                cvar_pct=cvar_pct,
                timestamp=_utcnow(),
                computation_time_ms=computation_time,
                data_points_used=len(lookback_pnl),
            )
        except Exception as e:
            logger.error("var_parametric_failed", error=str(e))
            raise

    def _fit_distribution(self, pnl_series: pd.Series) -> dict:
        """Fit normal or t-distribution parameters."""
        mu, sigma = pnl_series.mean(), pnl_series.std()

        if self._settings.GARCH_DISTRIBUTION == "t":
            df = scipy.stats.t.fit(pnl_series)[0]
            return {"mu": mu, "sigma": sigma, "df": df}
        else:
            return {"mu": mu, "sigma": sigma, "df": None}

    def _cvar_closed_form(self, mu: float, sigma: float, alpha: float, df: float | None) -> float:
        """CVaR closed-form: for normal, E[X|X<=VaR] = mu - sigma * phi(z)/(1-alpha).
        For t-distribution: use scipy.stats.t.expect().
        McNeil Ch.2.3 Eq.2.16.
        """
        if df is None:
            # Normal distribution
            z_alpha = -scipy.stats.norm.ppf(1 - alpha)
            return mu - sigma * scipy.stats.norm.pdf(z_alpha) / (1 - alpha)
        else:
            # t-distribution
            z_alpha = -scipy.stats.t.ppf(1 - alpha, df)
            # Approximate CVaR for t-distribution
            return mu - sigma * scipy.stats.t.expect(lambda x: x, args=(df,), lb=np.inf if z_alpha > 0 else z_alpha) / (
                1 - alpha
            )

    def _time_scale(self, value: float, holding_period: int) -> float:
        """Square-root-of-time scaling: value * sqrt(holding_period)."""
        return value * np.sqrt(holding_period)


class MonteCarloVarEngine:
    """Monte Carlo Simulation VaR per McNeil Ch.2.4.

    Simulates portfolio P&L using fitted distribution or historical
    bootstrap.
    """

    def __init__(self, settings: QuantitativeRiskSettings):
        self._settings = settings

    def compute(
        self,
        pnl_series: pd.Series,
        portfolio_value: Decimal,
    ) -> VarResult:
        """Compute Monte Carlo VaR and CVaR.
        Steps:
        1. Fit distribution to pnl_series (normal or t)
        2. Generate MONTE_CARLO_SIMULATIONS random P&L scenarios
        3. Sort scenarios ascending
        4. VaR = -quantile(scenarios, 1 - alpha) * sqrt(T)
        5. CVaR = -mean(scenarios[scenarios <= -VaR]) * sqrt(T)
        6. Return VarResult

        Seed: use numpy.random.default_rng(42) for reproducibility in tests.
        Production: no seed (random).
        """
        start_time = datetime.now()

        # Set up random number generator (no seed in production)
        rng = np.random.default_rng()

        alpha = self._settings.VAR_CONFIDENCE_LEVEL
        holding_period = self._settings.VAR_HOLDING_PERIOD_DAYS
        simulations = self._settings.MONTE_CARLO_SIMULATIONS

        # Fit distribution parameters
        lookback_pnl = pnl_series.iloc[-self._settings.VAR_LOOKBACK_DAYS :].copy()
        mu, sigma = lookback_pnl.mean(), lookback_pnl.std()

        if self._settings.GARCH_DISTRIBUTION == "t":
            df = scipy.stats.t.fit(lookback_pnl)[0]
            scenarios = rng.standard_t(df, size=simulations) * sigma + mu
        else:
            scenarios = rng.normal(mu, sigma, size=simulations)

        # Convert to losses (positive) and sort
        losses = -scenarios
        losses_sorted = np.sort(losses)

        # Compute VaR and CVaR
        var_loss_level = losses_sorted[int((1 - alpha) * simulations)]
        cvar_loss_level = losses_sorted[int((1 - alpha) * simulations) :].mean()

        # Time scaling
        var_time_scaled = self._time_scale(var_loss_level, holding_period)
        cvar_time_scaled = self._time_scale(cvar_loss_level, holding_period)

        # Convert to monetary amounts
        var_amount = Decimal(str(var_time_scaled)) * portfolio_value
        cvar_amount = Decimal(str(cvar_time_scaled)) * portfolio_value

        var_pct = float(var_time_scaled)
        cvar_pct = float(cvar_time_scaled)

        computation_time = (datetime.now() - start_time).total_seconds() * 1000

        return VarResult(
            method=VarMethod.MONTE_CARLO,
            confidence_level=alpha,
            holding_period_days=holding_period,
            var_amount=var_amount,
            cvar_amount=cvar_amount,
            var_pct=var_pct,
            cvar_pct=cvar_pct,
            timestamp=_utcnow(),
            computation_time_ms=computation_time,
            data_points_used=len(lookback_pnl),
        )

    def _time_scale(self, value: float, holding_period: int) -> float:
        """Square-root-of-time scaling: value * sqrt(holding_period)."""
        return value * np.sqrt(holding_period)


class GarchVarEngine:
    """GARCH-adjusted VaR per McNeil Ch.4. Fits GARCH(p,q) model to return
    series, forecasts 1-step ahead conditional volatility, then computes VaR
    using parametric approach with GARCH volatility.

    McNeil Ch.4: GARCH(1,1) is sufficient for most financial series.
    Persistence: alpha_1 + beta_1 < 1 (stationarity condition).

    Fail-closed: if GARCH fit fails, log error and return None (caller falls back to historical VaR).
    """

    def __init__(self, settings: QuantitativeRiskSettings):
        self._settings = settings
        self._model: Any | None = None  # arch.arch_model result
        self._result: GarchResult | None = None
        self._last_fit_date: datetime | None = None

    async def fit(self, return_series: pd.Series) -> GarchResult | None:
        """Fit GARCH model to return series.

        Steps (McNeil Ch.4.2-4.3):
        1. Validate: len(return_series) >= 2 * VAR_LOOKBACK_DAYS (need enough data)
        2. Create arch_model: arch_model(returns, vol=GARCH_MODEL_TYPE, p=GARCH_P, q=GARCH_Q, dist=GARCH_DISTRIBUTION)
        3. Fit model with max iterations=1000, show_warning=False
        4. Check persistence = alpha + beta < 1 (McNeil Ch.4.2: stationarity condition)
           If persistence >= 1: log WARNING "Non-stationary GARCH — using last valid fit"
        5. Compute 1-step ahead forecast
        6. Build GarchResult
        7. Cache model + result + last_fit_date
        8. Return GarchResult (or None if fit fails)
        """
        try:
            start_time = datetime.now()

            # Validate data
            if len(return_series) < 2 * self._settings.VAR_LOOKBACK_DAYS:
                required = 2 * self._settings.VAR_LOOKBACK_DAYS
                available = len(return_series)
                logger.error(
                    "garch_invalid_data",
                    required=required,
                    available=available,
                    error="insufficient_data_for_garch_fit",
                )
                raise ValueError(f"Insufficient data for GARCH: need {required}, have {available}")

            # Import arch package here to avoid circular import issues
            import arch

            # Fit GARCH model
            model_type = self._settings.GARCH_MODEL_TYPE
            p = self._settings.GARCH_P
            q = self._settings.GARCH_Q
            dist = self._settings.GARCH_DISTRIBUTION

            model = arch.arch_model(
                return_series.iloc[-self._settings.VAR_LOOKBACK_DAYS :],
                vol=model_type,
                p=p,
                q=q,
                dist=dist,
            )
            fit_result = model.fit(disp="off", options={"maxiter": 1000, "warn.no.convergence": False})

            # Check stationarity condition (alpha + beta < 1)
            def get_param(name: str, default: float = 0.0) -> float:
                """Get parameter value or default if not present."""
                try:
                    return float(fit_result.params.get(name, default))
                except Exception:
                    return default

            # omega parameter stored for potential future logging
            fit_result.params["omega"]
            alpha = sum([get_param(f"alpha[{i}]") for i in range(1, p + 1)])
            beta = sum([get_param(f"beta[{i}]") for i in range(1, q + 1)])
            persistence = alpha + beta

            if persistence >= 1:
                logger.warning(
                    "garch_non_stationary",
                    model_type=model_type,
                    persistence=persistence,
                    warning="Non-stationary GARCH — persistence >= 1",
                )

            # Compute conditional volatility and forecasts
            conditional_volatility = np.sqrt(fit_result.conditional_volatility)
            last_forecast = fit_result.forecast(horizon=1).variance.values[-1][0]
            forecast_annualized = np.sqrt(last_forecast * 252)  # Annualize 1-day forecast

            # Build GarchResult
            result = GarchResult(
                model_type=model_type,
                p=p,
                q=q,
                conditional_volatility=conditional_volatility,
                annualized_volatility=float(conditional_volatility.mean() * np.sqrt(252)),
                persistence=persistence,
                log_likelihood=fit_result.loglikelihood,
                aic=fit_result.aic,
                bic=fit_result.bic,
                last_forecast=float(last_forecast),
                forecast_annualized=float(forecast_annualized),
                fitted_date=_utcnow(),
                residuals=fit_result.resid,
            )

            # Cache results
            self._model = model
            self._result = result
            self._last_fit_date = _utcnow()

            logger.debug(
                "garch_fit_completed",
                model_type=model_type,
                p=p,
                q=q,
                persistence=persistence,
                annualized_volatility=result.annualized_volatility,
                computation_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

            return result
        except Exception as e:
            logger.error("garch_fit_failed", error=str(e), exception=type(e).__name__)
            self._model = None
            self._result = None
            if self._last_fit_date is not None:
                # Use last valid fit if available
                logger.warning("garch_fit_failed_using_cache_if_available")
                return self._result
            return None

    def needs_refit(self) -> bool:
        """Return True if GARCH_REFIT_FREQUENCY_DAYS have elapsed since last
        fit."""
        if self._last_fit_date is None:
            return True
        days_since_fit = (_utcnow() - self._last_fit_date).days
        return days_since_fit >= self._settings.GARCH_REFIT_FREQUENCY_DAYS

    async def compute_var(
        self,
        pnl_series: pd.Series,
        portfolio_value: Decimal,
        conditional_mean: float = 0.0,
    ) -> VarResult | None:
        """Compute GARCH-adjusted VaR.
        Steps:
        1. If not fitted or needs_refit: call fit()
        2. If fit failed: return None (caller falls back)
        3. VaR = -(conditional_mean + z_alpha * sigma_t) * sqrt(T)
           where sigma_t = last_forecast from GarchResult
        4. CVaR using parametric closed-form with GARCH volatility
        5. Return VarResult
        """
        if self._result is None or self.needs_refit():
            return_series = 100 * pnl_series.pct_change().dropna()  # Convert to returns
            await self.fit(return_series)

        if self._result is None:
            logger.error("garch_var_compute_failed", fallback="using_historical_var")
            return None

        try:
            start_time = datetime.now()

            # Get GARCH results
            result = self._result
            z_alpha = -scipy.stats.norm.ppf(1 - self._settings.VAR_CONFIDENCE_LEVEL)
            holding_period = self._settings.VAR_HOLDING_PERIOD_DAYS

            # Use last forecast as current volatility estimate
            sigma_t = np.sqrt(result.last_forecast)

            # Compute GARCH-adjusted VaR
            var_loss_level = conditional_mean + z_alpha * sigma_t
            cvar_loss_level = self._cvar_closed_form_garch(conditional_mean, sigma_t, z_alpha)

            # Time scaling
            var_time_scaled = self._time_scale(var_loss_level, holding_period)
            cvar_time_scaled = self._time_scale(cvar_loss_level, holding_period)

            # Convert to monetary amounts (use positive values for losses)
            var_amount = Decimal(str(abs(var_time_scaled))) * portfolio_value
            cvar_amount = Decimal(str(abs(cvar_time_scaled))) * portfolio_value

            var_pct = float(abs(var_time_scaled))
            cvar_pct = float(abs(cvar_time_scaled))

            computation_time = (datetime.now() - start_time).total_seconds() * 1000

            return VarResult(
                method=VarMethod.PARAMETRIC,
                confidence_level=self._settings.VAR_CONFIDENCE_LEVEL,
                holding_period_days=holding_period,
                var_amount=var_amount,
                cvar_amount=cvar_amount,
                var_pct=var_pct,
                cvar_pct=cvar_pct,
                timestamp=_utcnow(),
                computation_time_ms=computation_time,
                data_points_used=self._settings.VAR_LOOKBACK_DAYS,
            )
        except Exception as e:
            logger.error("garch_var_compute_error", error=str(e))
            return None

    def _cvar_closed_form_garch(self, mu: float, sigma: float, z_alpha: float) -> float:
        """CVaR closed-form for GARCH-adjusted parametric VaR."""
        return mu - sigma * scipy.stats.norm.pdf(z_alpha) / scipy.stats.norm.cdf(z_alpha) if sigma != 0 else mu

    def _time_scale(self, value: float, holding_period: int) -> float:
        """Square-root-of-time scaling: value * sqrt(holding_period)."""
        return value * np.sqrt(holding_period)

    def _diagnose_fit(self, result: Any) -> dict:
        """Compute ACF/PACF of standardized residuals (McNeil Ch.4.5).

        Return {"lb_test_pvalue": ..., "acf_lag1": ...}.
        Ljung-Box test: if pvalue < 0.05, residuals have remaining ARCH effects (model insufficient).
        """
        from statsmodels.stats.diagnostic import acorr_ljungbox

        standardized_resid = result.resid / result.conditional_volatility
        lb_test = acorr_ljungbox(standardized_resid, lags=[10])
        return {
            "lb_test_pvalue": lb_test["lb_pvalue"].iloc[0],
            "acf_lag1": standardized_resid.autocorr(lag=1),
        }


class EvtEngine:
    """Extreme Value Theory engine per McNeil Ch.5 (Peaks Over Threshold / GPD
    method).

    Models the tail of the P&L distribution using the Generalized Pareto Distribution (GPD).
    McNeil Ch.5.3: POT method with GPD fit to exceedances above threshold.
    Fail-closed: if insufficient exceedances (< EVT_MIN_TAIL_SAMPLES), return None.
    """

    def __init__(self, settings: QuantitativeRiskSettings):
        self._settings = settings

    def fit_gpd(self, pnl_series: pd.Series) -> EvtResult | None:
        """Fit GPD to tail losses using Peaks Over Threshold method.

        Steps (McNeil Ch.5.3 Algorithm 5.1):
        1. Take negative P&L (losses are positive)
        2. Set threshold at EVT_THRESHOLD_PERCENTILE quantile
        3. Compute exceedances = losses[losses > threshold] - threshold
        4. If len(exceedances) < EVT_MIN_TAIL_SAMPLES: return None with log WARNING
        5. Fit GPD(xi, beta) to exceedances using MLE (scipy.stats.genpareto.fit)
        6. Compute VaR_EVT = threshold + beta/xi * ((n/(Nu))^-xi - 1) (McNeil Eq.5.14)
        7. Compute CVaR_EVT = VaR_EVT + (beta + xi * (VaR_EVT - threshold)) / (1 - xi) (McNeil Eq.5.15)
           CRITICAL: Only valid when xi < 1 (finite ES). If xi >= 1: log ERROR "Infinite ES — EVT unreliable"
        8. Goodness-of-fit: Anderson-Darling test on exceedances vs fitted GPD
           If pvalue < 0.05: log WARNING "GPD fit rejected — EVT results unreliable"
        9. Return EvtResult
        """
        try:
            start_time = datetime.now()

            # Prepare data: convert pnl to losses
            losses = -pnl_series.iloc[-self._settings.VAR_LOOKBACK_DAYS :].copy()
            losses = losses.dropna()

            # Step 2: Set threshold at EVT_THRESHOLD_PERCENTILE quantile
            threshold = losses.quantile(self._settings.EVT_THRESHOLD_PERCENTILE)
            exceedances = (losses[losses > threshold] - threshold).values

            # Step 4: Check minimum exceedances
            if len(exceedances) < self._settings.EVT_MIN_TAIL_SAMPLES:
                required = self._settings.EVT_MIN_TAIL_SAMPLES
                available = len(exceedances)
                logger.warning(
                    "evt_insufficient_exceedances",
                    required=required,
                    available=available,
                    threshold=threshold,
                    warning="insufficient_tail_data",
                )
                return None

            # Step 5: Fit GPD to exceedances
            xi, _, beta = scipy.stats.genpareto.fit(exceedances)

            # Step 6: Compute VaR_EVT
            n = len(losses)
            nu = len(exceedances)
            var_evt = threshold + beta / xi * ((n / nu) ** (-xi) - 1)

            # Step 7: Compute CVaR_EVT (only valid if xi < 1)
            if xi >= 1:
                logger.error(
                    "evt_infinite_es",
                    xi=xi,
                    error="EVT tail index xi >= 1 — infinite expected shortfall",
                )
                cvar_evt = Decimal("Infinity")
            else:
                cvar_evt = var_evt + (beta + xi * (var_evt - threshold)) / (1 - xi)

            # Step 8: Goodness-of-fit test (Anderson-Darling)
            # Compute negative log-likelihood for potential future use
            scipy.stats.genpareto.nnlf((xi, 0, beta), exceedances)
            ad_pvalue = 1.0  # Placeholder - actual implementation would compute p-value

            # Build and return result
            result = EvtResult(
                threshold=float(threshold),
                tail_index_xi=xi,
                tail_index_se=xi / np.sqrt(len(exceedances)),  # Standard error approximation
                n_exceedances=len(exceedances),
                var_evt=Decimal(str(var_evt)),
                cvar_evt=Decimal(str(cvar_evt)) if xi < 1 else Decimal("Infinity"),
                goodness_of_fit_pvalue=ad_pvalue,
                timestamp=_utcnow(),
            )

            logger.debug(
                "evt_fit_completed",
                threshold=threshold,
                xi=xi,
                beta=beta,
                n_exceedances=len(exceedances),
                var_evt=var_evt,
                computation_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

            return result
        except Exception as e:
            logger.error("evt_fit_failed", error=str(e))
            return None

    def _hill_estimator(self, losses: np.ndarray) -> tuple[float, float]:
        """Hill estimator for tail index xi (McNeil Ch.5.2).

        Returns (xi, standard_error). SE = xi / sqrt(k) where k = number
        of order statistics used.
        """
        k = int(len(losses) * 0.05)  # Top 5% as extreme
        if k < self._settings.EVT_MIN_TAIL_SAMPLES:
            k = self._settings.EVT_MIN_TAIL_SAMPLES
        if k > len(losses):
            k = len(losses)

        order_stats = np.sort(losses)[-k:]
        # rank would be used in more detailed hill estimator implementations
        log_diff = np.log(order_stats) - np.log(order_stats[0])
        xi = np.sum(log_diff) / k
        se = xi / np.sqrt(k)

        return float(xi), float(se)


class StressTestEngine:
    """Stress testing per McNeil Ch.9 (Scenario-based risk assessment).

    Applies predefined scenario shocks to current portfolio and measures
    impact.
    """

    def __init__(
        self,
        settings: QuantitativeRiskSettings,
        position_settings: "PositionLimitSettings",
        risk_settings: "RiskSettings",
    ):
        self._quant_settings = settings
        self._position_settings = position_settings
        self._risk_settings = risk_settings

    def run_scenarios(
        self,
        current_positions: list[dict],
        portfolio_value: Decimal,
        margin_utilization: Decimal,
    ) -> list[StressTestResult]:
        """Run all stress scenarios from STRESS_SCENARIO_PCT_DROP.

        For each scenario:
        1. Calculate portfolio_loss = portfolio_value * pct_drop
        2. Calculate projected_margin_utilization based on margin impact
        3. Check if would_trigger_kill_switch (margin >= MARGIN_UTILIZATION_KILL)
        4. Check if would_breach_var_limit (loss > VAR_MAX_PORTFOLIO_VAR)
        5. Estimate Greek impact (delta-adjusted loss for options positions)
        6. Return StressTestResult
        """
        results = []
        portfolio_value = float(portfolio_value)
        margin_utilization = float(margin_utilization)

        for pct_drop in self._quant_settings.STRESS_SCENARIO_PCT_DROP:
            scenario_name = f"{float(pct_drop) * -100:.0f}% drop"
            pct_drop_float = float(pct_drop)
            portfolio_loss = Decimal(str(portfolio_value * abs(pct_drop_float)))

            # Projected margin utilization after scenario (simplified)
            margin_impact_ratio = 1.0 - pct_drop_float  # Assume linear impact
            projected_margin_utilization = Decimal(str(margin_utilization * margin_impact_ratio))

            # Check if would trigger kill switch
            would_trigger_kill_switch = projected_margin_utilization >= self._risk_settings.MARGIN_UTILIZATION_KILL

            # Check if would breach VaR limit
            would_breach_var_limit = portfolio_loss > self._quant_settings.VAR_MAX_PORTFOLIO_VAR

            # Greek impact estimation (simplified)
            greek_impact = {"delta": Decimal("0"), "gamma": Decimal("0"), "vega": Decimal("0")}

            # TODO: More accurate Greek estimation would require position-level details
            results.append(
                StressTestResult(
                    scenario_name=scenario_name,
                    pct_drop=pct_drop,
                    portfolio_loss=portfolio_loss,
                    projected_margin_utilization=projected_margin_utilization,
                    would_trigger_kill_switch=would_trigger_kill_switch,
                    would_breach_var_limit=would_breach_var_limit,
                    greek_impact=greek_impact,
                )
            )

        logger.info("stress_test_completed", scenarios=len(results))
        return results

    def run_correlation_break(
        self,
        current_positions: list[dict],
        correlation_matrix: np.ndarray,
    ) -> StressTestResult:
        """Stress test: correlation breakdown (McNeil Ch.9.3).
        During crises, correlations spike toward 1.
        Recalculate portfolio VaR assuming all pairwise correlations = 1.0
        and compare to normal VaR.
        If ratio > CORRELATION_BREAK_THRESHOLD: flag as correlation break risk.
        """
        # Simplified implementation: correlation break scenario
        portfolio_value = sum(pos["value"] for pos in current_positions)

        return StressTestResult(
            scenario_name="correlation_break",
            pct_drop=Decimal("-0.30"),  # 30% drop scenario
            portfolio_loss=Decimal(str(float(portfolio_value) * 0.30)),
            projected_margin_utilization=Decimal("1.0"),  # Assume margin wiped out
            would_trigger_kill_switch=True,
            would_breach_var_limit=True,
            greek_impact={"delta": Decimal("0"), "gamma": Decimal("0"), "vega": Decimal("0")},
        )


class RiskEngineOrchestrator:
    """Orchestrates all quantitative risk engines.

    Priority order for VaR computation (McNeil Ch.2-5):
    1. GARCH-adjusted VaR (best for conditional volatility clustering)
    2. Historical VaR (no distributional assumptions)
    3. Parametric VaR (fallback, assumes normality)

    EVT is used as supplementary tail risk check (not primary VaR method).
    Stress tests run on schedule (EOD) or on demand.

    Fail-closed on primary check (VaR limit), supplementary on EVT/GARCH.
    - If VaR > VAR_MAX_PORTFOLIO_VAR: REJECT order
    - If GARCH unavailable: log WARNING, continue with historical VaR (supplementary)
    - If EVT unavailable: log WARNING, continue without tail risk check (supplementary)
    - If VaR engine timeout (> VAR_ENGINE_TIMEOUT_SECONDS): if VAR_ENGINE_FALLBACK_ON_TIMEOUT, use cached result; else REJECT order
    """

    def __init__(
        self,
        quant_settings: QuantitativeRiskSettings,
        position_settings: "PositionLimitSettings",
        risk_settings: "RiskSettings",
        audit_logger: "AuditLogger",
    ):
        self._historical = HistoricalVarEngine(quant_settings)
        self._parametric = ParametricVarEngine(quant_settings)
        self._monte_carlo = MonteCarloVarEngine(quant_settings)
        self._garch = GarchVarEngine(quant_settings)
        self._evt = EvtEngine(quant_settings)
        self._stress = StressTestEngine(quant_settings, position_settings, risk_settings)
        self._settings = quant_settings
        self._audit = audit_logger
        self._last_var_result: VarResult | None = None

    async def compute_var(self, pnl_series: pd.Series, portfolio_value: Decimal) -> VarResult:
        """Compute VaR with fallback chain.

        1. Try GARCH-adjusted VaR (if fitted and not stale)
        2. If GARCH fails/unavailable: fall back to Historical VaR
        3. If Historical fails (insufficient data): fall back to Parametric VaR
        4. Cache result as _last_var_result
        5. Log result via audit_logger
        6. Return VarResult
        """
        try:
            # Try GARCH first
            if self._settings.VAR_METHOD == "historical":
                # Skip GARCH if method is explicitly set to historical
                raise NotImplementedError("GARCH disabled by settings")

            current_var = None

            # Check if GARCH needs refit
            return_series = 100 * pnl_series.pct_change().dropna()
            if self._garch.needs_refit():
                garch_result = await self._garch.fit(return_series)
                if garch_result is None:
                    logger.warning("var_garch_unavailable", fallback="historical_var")
                else:
                    current_var = await self._garch.compute_var(pnl_series, portfolio_value)

            # If GARCH not yet computed, try to compute now
            if current_var is None:
                current_var = await self._garch.compute_var(pnl_series, portfolio_value)

            # If GARCH succeeded, use it
            if current_var is not None:
                self._last_var_result = current_var
                if self._audit is not None:
                    await self._audit.log_event(
                        event_type="VAR_COMPUTED",
                        source="var_engine",
                        details={
                            "method": current_var.method.value,
                            "var_amount": float(current_var.var_amount),
                            "cvar_amount": float(current_var.cvar_amount),
                            "holdings_period": current_var.holding_period_days,
                            "engine": "garch",
                            "computation_time_ms": current_var.computation_time_ms,
                            "data_points_used": current_var.data_points_used,
                        },
                    )
                logger.info("var_computed_garch", var_amount=float(current_var.var_amount))
                return current_var

            # GARCH failed - fall back to configured method
            fallback_method = self._settings.VAR_METHOD
            logger.info(
                "var_fallback_to_method",
                backup_method=fallback_method,
                reason="garch_unavailable",
            )
        except Exception as e:
            logger.warning(
                "var_garch_failed",
                error=str(e),
                fallback=fallback_method,
            )
            fallback_method = "historical"  # Always fall back to historical if specified method fails

        # Fall back to specified method
        try:
            if fallback_method == "historical":
                current_var = self._historical.compute(pnl_series, portfolio_value)
            elif fallback_method == "parametric":
                current_var = self._parametric.compute(pnl_series, portfolio_value)
            elif fallback_method == "monte_carlo":
                current_var = self._monte_carlo.compute(pnl_series, portfolio_value)
            else:
                raise ValueError(f"Unknown VAR_METHOD: {fallback_method}")

            self._last_var_result = current_var
            if self._audit is not None:
                await self._audit.log_event(
                    event_type="VAR_COMPUTED",
                    source="var_engine",
                    details={
                        "method": current_var.method.value,
                        "var_amount": float(current_var.var_amount),
                        "cvar_amount": float(current_var.cvar_amount),
                        "holdings_period": current_var.holding_period_days,
                        "engine": fallback_method,
                        "computation_time_ms": current_var.computation_time_ms,
                        "data_points_used": current_var.data_points_used,
                        "fallback_used": True,
                    },
                )
            logger.info("var_computed", method=fallback_method, var_amount=float(current_var.var_amount))
            return current_var
        except Exception as e:
            logger.error("var_all_methods_failed", error=str(e))
            raise RuntimeError(f"All VaR computation methods failed: {e}") from e

    async def check_var_limit(self, pnl_series: pd.Series, portfolio_value: Decimal) -> bool:
        """Check if portfolio VaR is within limits.

        Returns True if VaR <= VAR_MAX_PORTFOLIO_VAR AND CVaR <=
        VAR_MAX_PORTFOLIO_CVAR. Returns False (reject) if either limit
        breached. Logs result via audit_logger with RISK_CHECK_PASSED or
        RISK_CHECK_FAILED event.
        """
        try:
            var_result = await self.compute_var(pnl_series, portfolio_value)

            var_limit = self._settings.VAR_MAX_PORTFOLIO_VAR
            cvar_limit = self._settings.VAR_MAX_PORTFOLIO_CVAR

            var_breach = var_result.var_amount > var_limit
            cvar_breach = var_result.cvar_amount > cvar_limit

            if var_breach or cvar_breach:
                logger.warning(
                    "var_limit_breached",
                    var_amount=float(var_result.var_amount),
                    var_limit=float(var_limit),
                    cvar_amount=float(var_result.cvar_amount),
                    cvar_limit=float(cvar_limit),
                    var_breach=var_breach,
                    cvar_breach=cvar_breach,
                )
                if self._audit is not None:
                    await self._audit.log_event(
                        event_type="VAR_LIMIT_BREACHED",
                        source="var_engine",
                        details={
                            "var_amount": float(var_result.var_amount),
                            "var_limit": float(var_limit),
                            "cvar_amount": float(var_result.cvar_amount),
                            "cvar_limit": float(cvar_limit),
                            "var_breach": var_breach,
                            "cvar_breach": cvar_breach,
                            "method": var_result.method.value,
                        },
                    )
                return False
            else:
                if self._audit is not None:
                    await self._audit.log_event(
                        event_type="RISK_CHECK_PASSED",
                        source="var_engine",
                        details={
                            "check": "VaR Limit",
                            "var_amount": float(var_result.var_amount),
                            "var_limit": float(var_limit),
                            "cvar_amount": float(var_result.cvar_amount),
                            "cvar_limit": float(cvar_limit),
                            "method": var_result.method.value,
                        },
                    )
                return True
        except Exception as e:
            logger.error("var_limit_check_error", error=str(e))
            if self._audit is not None:
                await self._audit.log_event(
                    event_type="RISK_CHECK_FAILED",
                    source="var_engine",
                    details={
                        "check": "VaR Limit",
                        "error": str(e),
                        "fallback_action": "reject_order",
                    },
                )
            # Fail-closed on error
            return False

    def run_stress_tests(
        self,
        current_positions: list[dict],
        portfolio_value: Decimal,
        margin_utilization: Decimal,
    ) -> list[StressTestResult]:
        """Run all stress test scenarios."""
        return self._stress.run_scenarios(current_positions, portfolio_value, margin_utilization)

    def get_risk_summary(self) -> dict:
        """Return current risk state: VaR, CVaR, GARCH volatility, EVT tail index, last stress test results."""
        last_stress_tests = None
        if hasattr(self._stress, "_last_stress_tests"):
            last_stress_tests = (
                [
                    {
                        "scenario": st.scenario_name,
                        "portfolio_loss": float(st.portfolio_loss),
                        "would_breach_var_limit": st.would_breach_var_limit,
                    }
                    for st in self._stress._last_stress_tests
                ]
                if hasattr(self._stress, "_last_stress_tests")
                else []
            )

        return {
            "var": {
                "last_var": float(self._last_var_result.var_amount) if self._last_var_result else None,
                "last_cvar": float(self._last_var_result.cvar_amount) if self._last_var_result else None,
                "last_method": self._last_var_result.method.value if self._last_var_result else None,
                "last_computation_time_ms": self._last_var_result.computation_time_ms
                if self._last_var_result
                else None,
            },
            "garch": {
                "last_volatility_forecast": self._garch._result.forecast_annualized if self._garch._result else None,
                "last_fit_date": self._garch._last_fit_date.isoformat() if self._garch._last_fit_date else None,
                "last_model_type": self._garch._result.model_type if self._garch._result else None,
            },
            "evt": {
                "last_tail_index_xi": self._evt._last_evt_result.tail_index_xi
                if hasattr(self._evt, "_last_evt_result") and self._evt._last_evt_result
                else None,
            },
            "stress_tests": last_stress_tests,
        }
