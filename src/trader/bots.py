from dataclasses import dataclass


@dataclass(frozen=True)
class Bot:
    number: int
    key: str
    name: str
    what: str
    commands: tuple[str, ...]


BOTS = (
    Bot(
        1,
        "notice",
        "Анонси бірж",
        "Ловить анонси Binance та Upbit (лістинги, делістинги, теги моніторингу, попередження) і за секунди торгує ф'ючерсом токена на Binance.",
        ("trader run", "trader replay YYYY-MM-DD", "trader research ticks"),
    ),
    Bot(
        2,
        "quant",
        "Квант",
        "135 індикаторів, математичних і патернових ознак по кожному ліквідному ф'ючерсу → дві моделі LightGBM ранжують токени → щодня ринково-нейтральна книга: "
        "30 лонгів найсильніших і до 30 шортів найслабших, шорти ≤ 4 %, бета-хедж через BTC, плече 2x, торгівля лише поза коридором 1 %.",
        (
            "trader quant paper --loop",
            "trader quant forward YYYY-MM-DD",
            "trader quant book YYYY-MM-DD",
            "trader quant day SYMBOL YYYY-MM-DD",
            "trader quant day SYMBOL --csv quotes.csv",
        ),
    ),
)
