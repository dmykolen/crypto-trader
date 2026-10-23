"""Notice/event classification on real exchange titles."""

from datetime import UTC, datetime

import pytest

from trader.services.events import EventType, Notice, classify

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def events(source: str, title: str) -> list[tuple[EventType, str]]:
    return [(e.type, e.token) for e in classify(Notice(source, "1", title, NOW))]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("콘크리트(CT) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)", [(EventType.UPBIT_KRW_LISTING, "CT")]),
        ("렌조(REZ) 신규 거래지원 안내 (USDT 마켓) (거래지원 개시 시점 추가 변경 안내)", [(EventType.UPBIT_LISTING, "REZ")]),
        (
            "헤미(HEMI), 유즈리스(USELESS) 신규 거래지원 안내 (BTC, USDT 마켓) (헤미(HEMI) 거래지원 취소 안내)",
            [(EventType.UPBIT_LISTING, "HEMI"), (EventType.UPBIT_LISTING, "USELESS")],
        ),
        (
            "BTC, USDT 마켓 신규 거래지원 안내 (BICO, BMT, NIL, GWEI) (BICO, BMT, NIL, GWEI 거래지원 개시 시점 추가 변경 안내)",
            [(EventType.UPBIT_LISTING, t) for t in ("BICO", "BMT", "NIL", "GWEI")],
        ),
        ("메타플렉스(MPLX) KRW 마켓 디지털 자산 추가", [(EventType.UPBIT_KRW_LISTING, "MPLX")]),
        ("BTC 마켓 디지털 자산 추가 (컴파운드 COMP, 스와이프 SXP, 헌트 HUNT)", [(EventType.UPBIT_LISTING, t) for t in ("COMP", "SXP", "HUNT")]),
        ("원화 마켓 디지털 자산 추가 (AXS, STX, FLOW, DAWN)", [(EventType.UPBIT_KRW_LISTING, t) for t in ("AXS", "STX", "FLOW", "DAWN")]),
        ("하이브달러(HBD) 거래 유의 종목 지정 안내", [(EventType.UPBIT_WARNING, "HBD")]),
        ("만트라(MANTRA) 거래 유의 종목 지정 기간 연장 안내", []),
        ("샌드박스(SAND) 거래 유의 종목 지정 해제 안내", [(EventType.UPBIT_WARNING_LIFTED, "SAND")]),
        ("질리카(ZIL) 거래지원 종료 안내 (11/16 15:00)", [(EventType.UPBIT_DELISTING, "ZIL")]),
        ("왁스(WAXP) 유의 촉구 안내", [(EventType.UPBIT_CAUTION, "WAXP")]),
        ("원화 마켓 신규 상장 (엑시인피니티(AXS))", [(EventType.UPBIT_KRW_LISTING, "AXS")]),
    ],
)
def test_upbit(title, expected):
    assert events("upbit", title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Binance Will List Hyperliquid (HYPE) with Seed Tag Applied", [(EventType.BINANCE_SPOT_LISTING, "HYPE")]),
        ("Binance Will Delist ICX, SCRT, STORJ on 2026-09-03", [(EventType.BINANCE_SPOT_DELISTING, t) for t in ("ICX", "SCRT", "STORJ")]),
        (
            "Binance Will Extend the Monitoring Tag to Include BICO & CVC on 2026-10-09",
            [(EventType.BINANCE_MONITORING_TAG, "BICO"), (EventType.BINANCE_MONITORING_TAG, "CVC")],
        ),
        (
            "Binance Futures Will Delist PTBUSDT and MITOUSDT USDⓈ-M Perpetual Contracts (2026-10-23)",
            [(EventType.BINANCE_PERP_DELISTING, "PTB"), (EventType.BINANCE_PERP_DELISTING, "MITO")],
        ),
        ("Notice of Removal of Spot Trading Pairs - 2026-10-23", []),
        ("Binance Futures Will Launch USDⓈ-Margined FOOUSDT Perpetual Contract", []),
    ],
)
def test_binance(title, expected):
    assert events("binance", title) == expected
