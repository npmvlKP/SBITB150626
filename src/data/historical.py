"""Resumable Historical Data Pipeline for NSE Bhavcopies - Phase 2."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
from dateutil.relativedelta import relativedelta

if TYPE_CHECKING:
    from src.data.event_log import MarketEvent

logger = logging.getLogger(__name__)


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================


class RedisProtocol(Protocol):
    """Protocol for Redis client."""

    async def get(self, key: str) -> bytes | None: ...
    async def setex(self, key: str, time: int | str, value: str | bytes) -> bool: ...


class EventWriterProtocol(Protocol):
    """Protocol for event writer."""

    async def write(self, event: MarketEvent) -> None: ...


class AuditLoggerProtocol(Protocol):
    """Protocol for audit logger."""

    async def info(self, msg: str, **kwargs: Any) -> None: ...
    async def error(self, msg: str, **kwargs: Any) -> None: ...
    async def warning(self, msg: str, **kwargs: Any) -> None: ...


# ============================================================================
# DATACLASSES
# ============================================================================


@dataclass
class DownloadResult:
    """Result of a historical data download operation."""

    total_dates: int = 0
    skipped: int = 0
    downloaded: int = 0
    failed: int = 0
    failed_dates: list[date] = field(default_factory=list)
    total_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "total_dates": self.total_dates,
            "skipped": self.skipped,
            "downloaded": self.downloaded,
            "failed": self.failed,
            "failed_dates": [d.isoformat() for d in self.failed_dates],
            "total_rows": self.total_rows,
        }


# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 2.0
RATE_LIMIT_DELAY: float = 1.1  # 1 request per second with buffer


# ============================================================================
# CLASS: AuditLogger
# ============================================================================


class AuditLogger:
    """Structured audit logger for historical pipeline operations."""

    def __init__(self, log_file: Path | None = None) -> None:
        """Initialize audit logger.

        Args:
            log_file: Optional file path for audit log output.
        """
        self.log_file = log_file
        self._buffer: list[str] = []
        self._run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    @property
    def run_id(self) -> str:
        """Get the current run ID."""
        return self._run_id

    async def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message with structured data."""
        await self._log("INFO", msg, **kwargs)

    async def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message with structured data."""
        await self._log("ERROR", msg, **kwargs)

    async def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message with structured data."""
        await self._log("WARNING", msg, **kwargs)

    async def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message with structured data."""
        await self._log("DEBUG", msg, **kwargs)

    async def _log(self, level: str, msg: str, **kwargs: Any) -> None:
        """Internal logging method."""
        import json as json_module

        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] [{self._run_id}] {msg}"

        if kwargs:
            log_entry += f" | {json_module.dumps(kwargs)}"

        logger.log(
            getattr(logging, level.lower(), logging.INFO),
            log_entry,
        )

        self._buffer.append(log_entry)

        if self.log_file:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(log_entry + "\n")
            except OSError:
                pass


# ============================================================================
# CLASS: BhavcopyParser
# ============================================================================


class BhavcopyParser:
    """Parser for NSE Bhavcopy CSV files."""

    # FO-specific column mapping
    FO_COLUMN_MAP: dict[str, str] = {
        "SYMBOL": "symbol",
        "INSTRUMENT": "instrument",
        "EXPIRY_DT": "expiry_date",
        "STRIKE_PR": "strike_price",
        "OPTION_TYP": "option_type",
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "SETTLE_PR": "settlement_price",
        "CONTRACTS": "contracts",
        "VAL_INLAKH": "value_in_lakhs",
        "OPEN_INT": "open_interest",
        "CHG_IN_OI": "change_in_oi",
        "TIMESTAMP": "timestamp",
    }

    # CM-specific column mapping
    CM_COLUMN_MAP: dict[str, str] = {
        "SYMBOL": "symbol",
        "SERIES": "series",
        "OPEN": "open",
        "HIGH": "high",
        "LOW": "low",
        "CLOSE": "close",
        "LAST": "last_price",
        "TURNOVER": "turnover",
        "NO_OF_TRADES": "num_trades",
        "DELIVERY": "delivery_quantity",
        "DELIV_PER": "delivery_percent",
    }

    def __init__(self, audit_logger: AuditLoggerProtocol | None = None) -> None:
        """Initialize parser.

        Args:
            audit_logger: Optional audit logger for operations.
        """
        self.audit_logger = audit_logger or AuditLogger()

    def parse_fo_csv(self, filepath: Path) -> pd.DataFrame:
        """Parse F&O Bhavcopy CSV file.

        Args:
            filepath: Path to the F&O CSV file.

        Returns:
            Parsed and filtered DataFrame with F&O derivatives data.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file format is invalid.
        """
        if not filepath.exists():
            raise FileNotFoundError(f"FO Bhavcopy file not found: {filepath}")

        logger.info(f"Parsing FO bhavcopy: {filepath}")

        df = pd.read_csv(filepath, skipinitialspace=True)
        df.columns = df.columns.str.strip()

        if df.empty:
            raise ValueError(f"Empty FO bhavcopy file: {filepath}")

        if "SYMBOL" not in df.columns:
            raise ValueError("Invalid FO bhavcopy format - missing SYMBOL column")

        original_count = len(df)

        df = df.rename(columns=self.FO_COLUMN_MAP)

        df["expiry_date"] = pd.to_datetime(df["expiry_date"], format="%d-%b-%Y", errors="coerce").dt.date

        df["option_type"] = df["option_type"].str.strip().str.upper()
        df["symbol"] = df["symbol"].str.strip()
        df["instrument"] = df["instrument"].str.strip().str.upper()

        filtered_df = df[
            (df["symbol"].isin(["NIFTY", "BANKNIFTY"])) & (df["instrument"].isin(["OPTIDX", "OPTSTK"]))
        ].copy()

        numeric_cols = ["open", "high", "low", "close", "open_interest", "contracts"]
        for col in numeric_cols:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors="coerce")

        filtered_df = self._validate_and_filter(filtered_df)

        filtered_count = len(filtered_df)
        dropped = original_count - filtered_count

        logger.info(
            f"Parsed FO bhavcopy: {filepath}",
            original=original_count,
            filtered=filtered_count,
            dropped=dropped,
        )

        return filtered_df

    def parse_cm_csv(self, filepath: Path) -> pd.DataFrame:
        """Parse Capital Market Bhavcopy CSV file.

        Args:
            filepath: Path to the CM CSV file.

        Returns:
            Parsed and filtered DataFrame with index constituent data.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file format is invalid.
        """
        if not filepath.exists():
            raise FileNotFoundError(f"CM Bhavcopy file not found: {filepath}")

        logger.info(f"Parsing CM bhavcopy: {filepath}")

        df = pd.read_csv(filepath, skipinitialspace=True)
        df.columns = df.columns.str.strip()

        if df.empty:
            raise ValueError(f"Empty CM bhavcopy file: {filepath}")

        if "SYMBOL" not in df.columns:
            raise ValueError("Invalid CM bhavcopy format - missing SYMBOL column")

        original_count = len(df)

        df = df.rename(columns=self.CM_COLUMN_MAP)

        df["symbol"] = df["symbol"].str.strip()
        df["series"] = df["series"].str.strip().str.upper()

        filtered_df = df[(df["symbol"].isin(["NIFTY 50", "NIFTY BANK"])) & (df["series"] == "INDEX")].copy()

        numeric_cols = [
            "open",
            "high",
            "low",
            "close",
            "last_price",
            "turnover",
        ]
        for col in numeric_cols:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors="coerce")

        filtered_df = self._validate_and_filter(filtered_df, is_cm=True)

        filtered_count = len(filtered_df)
        dropped = original_count - filtered_count

        logger.info(
            f"Parsed CM bhavcopy: {filepath}",
            original=original_count,
            filtered=filtered_count,
            dropped=dropped,
        )

        return filtered_df

    def _validate_and_filter(self, df: pd.DataFrame, is_cm: bool = False) -> pd.DataFrame:
        """Validate and filter DataFrame rows.

        Args:
            df: Input DataFrame.
            is_cm: Whether this is CM data (different validation rules).

        Returns:
            Validated and filtered DataFrame.
        """
        if df.empty:
            return df

        mask = pd.Series(True, index=df.index)

        if "open" in df.columns and "high" in df.columns:
            mask &= df["open"] <= df["high"]
        if "low" in df.columns and "high" in df.columns:
            mask &= df["low"] <= df["high"]
        if "volume" in df.columns:
            mask &= df["volume"] >= 0
        if "open_interest" in df.columns:
            mask &= df["open_interest"] >= 0
        if "close" in df.columns:
            mask &= df["close"] > 0

        if not is_cm and "strike_price" in df.columns:
            mask &= df["strike_price"] > 0

        invalid_count = (~mask).sum()
        if invalid_count > 0:
            logger.debug(f"Filtered {invalid_count} invalid rows")

        return df[mask].copy()


# ============================================================================
# CLASS: BhavcopyDownloader
# ============================================================================


class BhavcopyDownloader:
    """Downloader for NSE Bhavcopies with resumable capability."""

    def __init__(
        self,
        settings: dict[str, Any],
        event_writer: EventWriterProtocol | None = None,
        audit_logger: AuditLoggerProtocol | None = None,
    ) -> None:
        """Initialize downloader.

        Args:
            settings: Application settings with data paths.
            event_writer: Optional event writer for market events.
            audit_logger: Optional audit logger for operations.
        """
        self.settings = settings
        self.event_writer = event_writer
        self.audit_logger = audit_logger or AuditLogger()
        self.parser = BhavcopyParser(self.audit_logger)

        self.fo_dir = Path(settings.get("DATA_DIR", "data/fo"))
        self.cm_dir = Path(settings.get("DATA_DIR", "data/cm"))

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure download directories exist."""
        self.fo_dir.mkdir(parents=True, exist_ok=True)
        self.cm_dir.mkdir(parents=True, exist_ok=True)
        self.audit_logger.info("Ensured download directories", fo=str(self.fo_dir), cm=str(self.cm_dir))

    async def download_fo_bhavcopies(
        self,
        start_date: date,
        end_date: date,
        skip_existing: bool = True,
    ) -> DownloadResult:
        """Download F&O Bhavcopies for date range.

        Args:
            start_date: Start date for download.
            end_date: End date for download.
            skip_existing: Skip dates with existing files.

        Returns:
            DownloadResult with statistics.
        """
        result = DownloadResult()

        trading_days = get_nse_trading_days(start_date, end_date)
        result.total_dates = len(trading_days)

        self.audit_logger.info(
            "Starting FO bhavcopy download",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            total_dates=result.total_dates,
        )

        for idx, trading_date in enumerate(trading_days):
            await self.audit_logger.info(f"[{idx + 1}/{result.total_dates}] Processing FO date: {trading_date}")

            if skip_existing:
                fo_file = self._get_fo_filepath(trading_date)
                if fo_file.exists():
                    await self.audit_logger.debug(f"Skipping existing FO file: {fo_file}")
                    result.skipped += 1
                    continue

            success, rows = await self._download_single_fo(trading_date)

            if success:
                result.downloaded += 1
                result.total_rows += rows

                if self.event_writer:
                    import uuid as uuid_module

                    from src.data.event_log import MarketEvent

                    event = MarketEvent(
                        event_id=uuid_module.uuid4(),
                        event_type="FO_BHAVCOPY",
                        event_time=datetime.combine(trading_date, datetime.min.time()),
                        schema_version=1,
                        payload={
                            "date": trading_date.isoformat(),
                            "rows": rows,
                            "status": "downloaded",
                        },
                        source="jugaad_data",
                    )
                    await self.event_writer.append(event)
            else:
                result.failed += 1
                result.failed_dates.append(trading_date)

            await asyncio.sleep(RATE_LIMIT_DELAY)

        await self.audit_logger.info(
            "Completed FO bhavcopy download",
            **result.to_dict(),
        )

        return result

    async def download_cm_bhavcopies(
        self,
        start_date: date,
        end_date: date,
        skip_existing: bool = True,
    ) -> DownloadResult:
        """Download CM Bhavcopies for date range.

        Args:
            start_date: Start date for download.
            end_date: End date for download.
            skip_existing: Skip dates with existing files.

        Returns:
            DownloadResult with statistics.
        """
        result = DownloadResult()

        trading_days = get_nse_trading_days(start_date, end_date)
        result.total_dates = len(trading_days)

        self.audit_logger.info(
            "Starting CM bhavcopy download",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            total_dates=result.total_dates,
        )

        for idx, trading_date in enumerate(trading_days):
            await self.audit_logger.info(f"[{idx + 1}/{result.total_dates}] Processing CM date: {trading_date}")

            if skip_existing:
                cm_file = self._get_cm_filepath(trading_date)
                if cm_file.exists():
                    await self.audit_logger.debug(f"Skipping existing CM file: {cm_file}")
                    result.skipped += 1
                    continue

            success, rows = await self._download_single_cm(trading_date)

            if success:
                result.downloaded += 1
                result.total_rows += rows

                if self.event_writer:
                    import uuid as uuid_module

                    from src.data.event_log import MarketEvent

                    event = MarketEvent(
                        event_id=uuid_module.uuid4(),
                        event_type="CM_BHAVCOPY",
                        event_time=datetime.combine(trading_date, datetime.min.time()),
                        schema_version=1,
                        payload={
                            "date": trading_date.isoformat(),
                            "rows": rows,
                            "status": "downloaded",
                        },
                        source="jugaad_data",
                    )
                    await self.event_writer.append(event)
            else:
                result.failed += 1
                result.failed_dates.append(trading_date)

            await asyncio.sleep(RATE_LIMIT_DELAY)

        await self.audit_logger.info(
            "Completed CM bhavcopy download",
            **result.to_dict(),
        )

        return result

    def _get_fo_filepath(self, trading_date: date) -> Path:
        """Get filepath for FO bhavcopy."""
        return self.fo_dir / f"fo_bhavcopy_{trading_date.isoformat()}.csv"

    def _get_cm_filepath(self, trading_date: date) -> Path:
        """Get filepath for CM bhavcopy."""
        return self.cm_dir / f"cm_bhavcopy_{trading_date.isoformat()}.csv"

    async def _download_single_fo(self, trading_date: date) -> tuple[bool, int]:
        """Download single FO bhavcopy with retry."""
        fo_file = self._get_fo_filepath(trading_date)

        for attempt in range(MAX_RETRIES):
            try:
                await self.audit_logger.debug(f"Downloading FO bhavcopy for {trading_date}, attempt {attempt + 1}")

                loop = asyncio.get_event_loop()
                nse_bhav = await loop.run_in_executor(
                    None,
                    self._sync_download_fo,
                    trading_date,
                    fo_file,
                )

                if nse_bhav:
                    df = self.parser.parse_fo_csv(fo_file)
                    await self.audit_logger.info(
                        f"Successfully downloaded FO bhavcopy: {trading_date}",
                        rows=len(df),
                    )
                    return True, len(df)

            except Exception as e:
                await self.audit_logger.warning(
                    f"FO download attempt {attempt + 1} failed",
                    date=trading_date.isoformat(),
                    error=str(e),
                    exc_info=True,
                )

                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    await asyncio.sleep(delay)

        await self.audit_logger.error(
            f"Failed to download FO bhavcopy after {MAX_RETRIES} attempts",
            date=trading_date.isoformat(),
        )
        return False, 0

    async def _download_single_cm(self, trading_date: date) -> tuple[bool, int]:
        """Download single CM bhavcopy with retry."""
        cm_file = self._get_cm_filepath(trading_date)

        for attempt in range(MAX_RETRIES):
            try:
                await self.audit_logger.debug(f"Downloading CM bhavcopy for {trading_date}, attempt {attempt + 1}")

                loop = asyncio.get_event_loop()
                nse_bhav = await loop.run_in_executor(
                    None,
                    self._sync_download_cm,
                    trading_date,
                    cm_file,
                )

                if nse_bhav:
                    df = self.parser.parse_cm_csv(cm_file)
                    await self.audit_logger.info(
                        f"Successfully downloaded CM bhavcopy: {trading_date}",
                        rows=len(df),
                    )
                    return True, len(df)

            except Exception as e:
                await self.audit_logger.warning(
                    f"CM download attempt {attempt + 1} failed",
                    date=trading_date.isoformat(),
                    error=str(e),
                    exc_info=True,
                )

                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    await asyncio.sleep(delay)

        await self.audit_logger.error(
            f"Failed to download CM bhavcopy after {MAX_RETRIES} attempts",
            date=trading_date.isoformat(),
        )
        return False, 0

    def _sync_download_fo(self, trading_date: date, filepath: Path) -> bool:
        """Synchronous FO download using jugaad-data."""
        try:
            from jugaad_data.nse import bhavcopy_fo_save

            bhavcopy_fo_save(trading_date, str(filepath.parent))
            return True
        except Exception:
            return False

    def _sync_download_cm(self, trading_date: date, filepath: Path) -> bool:
        """Synchronous CM download using jugaad-data."""
        try:
            from jugaad_data.nse import bhavcopy_cm_save

            bhavcopy_cm_save(trading_date, str(filepath.parent))
            return True
        except Exception:
            return False


# ============================================================================
# FUNCTION: get_nse_trading_days
# ============================================================================

_redis_client: RedisProtocol | None = None


def set_redis_client(client: RedisProtocol | None) -> None:
    """Set the Redis client for caching."""
    global _redis_client
    _redis_client = client


def get_nse_trading_days(start: date, end: date) -> list[date]:
    """Get list of NSE trading days between start and end dates.

    Uses Redis caching with 24h TTL for the trading days list.

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        List of trading days (excluding weekends and NSE holidays).
    """
    import json as json_module

    cache_key = f"nse_trading_days:{start.isoformat()}:{end.isoformat()}"

    if _redis_client is not None:
        try:
            import asyncio

            cached = asyncio.run(_redis_client.get(cache_key))
            if cached:
                days = json_module.loads(cached)
                logger.debug(f"Cache hit for trading days: {cache_key}")
                return [date.fromisoformat(d) for d in days]
        except Exception as e:
            logger.warning(f"Redis cache error: {e}")

    trading_days = _calculate_trading_days(start, end)

    if _redis_client is not None:
        try:
            import asyncio

            cache_value = json_module.dumps([d.isoformat() for d in trading_days])
            asyncio.run(_redis_client.setex(cache_key, 86400, cache_value))
            logger.debug(f"Cached trading days: {cache_key}")
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")

    return trading_days


def _calculate_trading_days(start: date, end: date) -> list[date]:
    """Calculate NSE trading days without caching."""
    try:
        from jugaad_data.nse import NSEHoliday

        nse_holidays = NSEHoliday()
        holidays = set(nse_holidays.list(start, end + relativedelta(years=1)))
    except Exception:
        holidays = set()

    trading_days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            trading_days.append(current)
        current += timedelta(days=1)

    return trading_days


# ============================================================================
# FUNCTION: run_historical_pipeline
# ============================================================================


async def run_historical_pipeline(
    settings: dict[str, Any],
    start_date: date,
    end_date: date,
    event_writer: EventWriterProtocol | None = None,
    audit_logger: AuditLoggerProtocol | None = None,
    skip_existing: bool = True,
) -> dict[str, DownloadResult]:
    """Run historical data pipeline for both FO and CM bhavcopies.

    Orchestrates download of F&O and CM bhavcopies for the specified date range.

    Args:
        settings: Application settings.
        start_date: Start date for download.
        end_date: End date for download.
        event_writer: Optional event writer for market events.
        audit_logger: Optional audit logger.
        skip_existing: Skip dates with existing files.

    Returns:
        Dictionary with 'fo' and 'cm' DownloadResult instances.
    """
    logger.info(
        "Starting historical data pipeline",
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )

    audit = audit_logger or AuditLogger()

    await audit.info(
        "=== Starting Historical Data Pipeline ===",
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )

    downloader = BhavcopyDownloader(
        settings=settings,
        event_writer=event_writer,
        audit_logger=audit,
    )

    fo_result = await downloader.download_fo_bhavcopies(
        start_date=start_date,
        end_date=end_date,
        skip_existing=skip_existing,
    )

    cm_result = await downloader.download_cm_bhavcopies(
        start_date=start_date,
        end_date=end_date,
        skip_existing=skip_existing,
    )

    await audit.info(
        "=== Historical Data Pipeline Complete ===",
        fo_result=fo_result.to_dict(),
        cm_result=cm_result.to_dict(),
    )

    logger.info(
        "Historical data pipeline completed",
        fo_downloaded=fo_result.downloaded,
        cm_downloaded=cm_result.downloaded,
    )

    return {
        "fo": fo_result,
        "cm": cm_result,
    }
