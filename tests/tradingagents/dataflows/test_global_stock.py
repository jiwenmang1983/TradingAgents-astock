import pytest
from tradingagents.dataflows.global_stock import _detect_market, _normalize_symbol


def test_detect_hk():
    assert _detect_market("02727.HK") == "hk"
    assert _detect_market("00700.HK") == "hk"
    assert _detect_market("00700") == "hk"
    assert _detect_market("07000") == "hk"


def test_detect_us():
    assert _detect_market("AAPL") == "us"
    assert _detect_market("AAPL.O") == "us"
    assert _detect_market("BABA.N") == "us"
    assert _detect_market("TSLA") == "us"


def test_detect_astock():
    assert _detect_market("600000") == "astock"
    assert _detect_market("000858") == "astock"
    assert _detect_market("688017") == "astock"
    assert _detect_market("600000.SS") == "astock"
    assert _detect_market("000001.SZ") == "astock"


def test_normalize_hk():
    assert _normalize_symbol("02727.HK") == ("2727", "02727", "hk")
    assert _normalize_symbol("07000") == ("7000", "07000", "hk")
    assert _normalize_symbol("00700") == ("0700", "00700", "hk")


def test_normalize_us():
    assert _normalize_symbol("AAPL") == ("AAPL", "AAPL", "us")
    assert _normalize_symbol("AAPL.O") == ("AAPL.O", "AAPL.O", "us")
    assert _normalize_symbol("BABA.N") == ("BABA.N", "BABA.N", "us")


def test_normalize_astock():
    assert _normalize_symbol("600000") == ("600000", "600000", "astock")
    assert _normalize_symbol("000001.SZ") == ("000001", "000001", "astock")