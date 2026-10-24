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
        "Індикатори, математичний аналіз, графічні та свічкові патерни → модель LightGBM вирішує, коли зайти, вийти або перевідкрити позицію з плечем на сотнях ф'ючерсів.",
        ("trader quant research", "trader quant day SYMBOL YYYY-MM-DD", "trader quant day SYMBOL --csv quotes.csv"),
    ),
)
