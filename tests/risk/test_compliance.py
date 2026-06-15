"""Tests for src/risk/compliance.py."""

from datetime import datetime

from src.risk.compliance import (
    ComplianceLevel,
    Segments,
    TradingSession,
    check_ops_threshold,
    format_algo_tag,
    get_trading_session,
    is_order_allowed,
    validate_symbol,
)


class TestGetTradingSession:
    """Tests for get_trading_session()."""

    def test_get_trading_session_regular_hours(self) -> None:
        """10:00 IST -> REGULAR for NSE."""
        now = datetime(2025, 6, 15, 10, 0, 0)
        result = get_trading_session(Segments.NSE, now)
        assert result == TradingSession.REGULAR

    def test_get_trading_session_closed(self) -> None:
        """20:00 IST -> CLOSED for NSE."""
        now = datetime(2025, 6, 15, 20, 0, 0)
        result = get_trading_session(Segments.NSE, now)
        assert result == TradingSession.CLOSED

    def test_get_trading_session_pre_market(self) -> None:
        """9:07 IST -> PRE_MARKET for NSE."""
        now = datetime(2025, 6, 15, 9, 7, 0)
        result = get_trading_session(Segments.NSE, now)
        assert result == TradingSession.PRE_MARKET

    def test_get_trading_session_post_market(self) -> None:
        """15:35 IST -> POST_MARKET for NSE."""
        now = datetime(2025, 6, 15, 15, 35, 0)
        result = get_trading_session(Segments.NSE, now)
        assert result == TradingSession.POST_MARKET

    def test_get_trading_session_mcx_morning(self) -> None:
        """10:00 IST for MCX morning -> REGULAR."""
        now = datetime(2025, 6, 15, 10, 0, 0)
        result = get_trading_session(Segments.MCX, now)
        assert result == TradingSession.REGULAR

    def test_get_trading_session_mcx_evening(self) -> None:
        """18:00 IST for MCX evening -> REGULAR."""
        now = datetime(2025, 6, 15, 18, 0, 0)
        result = get_trading_session(Segments.MCX, now)
        assert result == TradingSession.REGULAR

    def test_get_trading_session_mcx_closed(self) -> None:
        """16:00 IST for MCX (between sessions) -> CLOSED."""
        now = datetime(2025, 6, 15, 16, 0, 0)
        result = get_trading_session(Segments.MCX, now)
        assert result == TradingSession.CLOSED


class TestIsOrderAllowed:
    """Tests for is_order_allowed()."""

    def test_is_order_allowed_regular(self) -> None:
        """REGULAR session -> True."""
        assert is_order_allowed(TradingSession.REGULAR) is True

    def test_is_order_allowed_pre_market(self) -> None:
        """PRE_MARKET session -> False."""
        assert is_order_allowed(TradingSession.PRE_MARKET) is False

    def test_is_order_allowed_post_market(self) -> None:
        """POST_MARKET session -> False."""
        assert is_order_allowed(TradingSession.POST_MARKET) is False

    def test_is_order_allowed_closed(self) -> None:
        """CLOSED session -> False."""
        assert is_order_allowed(TradingSession.CLOSED) is False


class TestCheckOpsThreshold:
    """Tests for check_ops_threshold()."""

    def test_check_ops_threshold_below_10(self) -> None:
        """5 OPS -> UNREGISTERED."""
        result = check_ops_threshold(5.0)
        assert result == ComplianceLevel.UNREGISTERED

    def test_check_ops_threshold_at_10(self) -> None:
        """10 OPS -> UNREGISTERED (at threshold, not above)."""
        result = check_ops_threshold(10.0)
        assert result == ComplianceLevel.UNREGISTERED

    def test_check_ops_threshold_above_10(self) -> None:
        """15 OPS -> REGISTERED (requires registration)."""
        result = check_ops_threshold(15.0)
        assert result == ComplianceLevel.REGISTERED


class TestValidateSymbol:
    """Tests for validate_symbol()."""

    def test_validate_symbol_nifty(self) -> None:
        """NIFTY in NSE -> True."""
        assert validate_symbol("NIFTY", Segments.NSE) is True

    def test_validate_symbol_banknifty(self) -> None:
        """BANKNIFTY in NSE -> True."""
        assert validate_symbol("BANKNIFTY", Segments.NSE) is True

    def test_validate_symbol_invalid(self) -> None:
        """AAPL in NSE -> False."""
        assert validate_symbol("AAPL", Segments.NSE) is False

    def test_validate_symbol_gold_mcx(self) -> None:
        """GOLD in MCX -> True."""
        assert validate_symbol("GOLD", Segments.MCX) is True

    def test_validate_symbol_case_insensitive(self) -> None:
        """Symbol check is case-insensitive."""
        assert validate_symbol("nifty", Segments.NSE) is True
        assert validate_symbol("NiFtY", Segments.NSE) is True


class TestFormatAlgoTag:
    """Tests for format_algo_tag()."""

    def test_format_algo_tag_normal(self) -> None:
        """Normal tag: MOMENTUM:V3."""
        result = format_algo_tag("MOMENTUM", "V3")
        assert result == "MOMENTUM:V3"

    def test_format_algo_tag_truncate(self) -> None:
        """Long tag truncated to 20 chars."""
        result = format_algo_tag("VERYLONGSNSTRATEGY", "V3")
        # Length check
        assert len(result) <= 20
        # Result should be truncated version - just check it's valid
        assert len(result) >= 3

    def test_format_algo_tag_exact_length(self) -> None:
        """Short tag unchanged."""
        result = format_algo_tag("MOM", "V3")
        assert result == "MOM:V3"

    def test_format_algo_tag_version_only_truncate(self) -> None:
        """If version is too long, truncate whole tag."""
        result = format_algo_tag("A", "VERYLONVERSION99", max_length=10)
        assert len(result) <= 10