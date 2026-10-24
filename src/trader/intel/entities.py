"""Entity linking: free text → Binance USDⓈ-M perpetual symbols.

Three kinds of evidence, strongest first: cashtags (`$SOL`), tickers in parentheses or next to a crypto word
(`Solana (SOL)`, `SOL price`, `SOL token`), and coin names/aliases (`Solana`, `Shiba Inu`). Names come from the
CoinGecko top-market-cap list cached in data/intel/, intersected with the perp universe; when several coins share a
ticker the highest-ranked one owns the name. Tickers or names that are ordinary words (ONE, GAS, SUN, MAGIC, AI,
PEOPLE…) only count with a cashtag or explicit crypto context.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from trader.core.config import settings


def _words(*chunks: str) -> frozenset[str]:
    return frozenset(" ".join(chunks).split())


AMBIGUOUS_TICKERS = _words(
    "ONE GAS SUN MAGIC AI ACE BANANA PEOPLE MOVE ME IO ID HOOK HIGH LOW TRUE CAKE DOG CAT BOND BLUR EDU FUN GOAT HOT KEY LIT MASK MAX",
    "NOT OM OP RARE REAL SUPER TON UNI USUAL WIN ANT ARK BAT COMBO COOKIE COW DEGEN ENJ FLOW GLM GMT HYPE ICE IP JOE LAYER MEME OG",
    "OMNI PIXEL PUMP RED SIGN SKATE SPELL SWELL THE TRUMP VIRTUAL WAL BANK BABY DEEP DOOD FORM GPS HOME INIT LA NIL PROMPT SOON TREE",
    "BID ARC POL ALPHA BEAM DATA EPIC GRASS LEVER LINK LOOM MAV POWER QUICK RAY ROSE SAFE TOKEN TRU UMA ACT DOGS NEIRO TURBO AVA",
    "HYPER NFT CHESS STORY SAND MANA NEAR WIF ZK ZRO ORCA BIO KAITO JUP BOME SLERF MYRO DUSK CHR COS FIS LQTY GAL MDT NKN REN",
    "SYN SYS TRB XAI AUCTION MINA PERP PORTAL HMSTR CATI MEW POPCAT PNUT SUNDOG DIA GHST KOMA MOCA PONKE QUAI RONIN SYRUP TAIKO X",
)
ALWAYS_CONTEXT = _words(
    "USD USDT USDC EUR CEO CTO CFO COO SEC ETF ETP CFTC FED FOMC GDP CPI API DAO DEX CEX TVL ATH APR APY KYC AML IPO FBI DOJ UK EU US USA",
    "NYSE NASDAQ UTC EST AMA SPAC IRS OCC FDIC IMF ECB BOJ PBOC MSCI OTC RWA AMM LLM GPU NFTS AI NFP HFT GTC SPX NDX DXY GPT ESG PCE PPI",
)
GENERIC_NAMES = _words(
    "one gas sun magic ace banana people move me io hook high low true cake dog cat bond blur edu fun goat hot key lit mask max near not",
    "real rare portal super ton uni usual flow ice joe layer meme omni pixel red render sign skate swell the trump virtual deep form home",
    "power quick safe token data epic grass alpha beam lever link loom mode blast scroll origin fetch ocean frax pool curve compound maker",
    "chain cash classic gala band nano dash neo icon harmony golem helium oasis sushi balancer stacks immutable sandbox jupiter orca",
    "wormhole status civic story theta mantle kava just four bounce canton comedian espresso humanity katana lighter midnight momentum",
    "movement plasma quant seeker sentient spark tagger treasure venus verge wax perle overtake bedrock lagrange tensor synapse euler",
    "astar holo lisk skale",
)
LOWERCASE_OK = _words("bitcoin ether ethereum solana dogecoin litecoin cardano ripple chainlink uniswap polkadot monero zcash tron shiba")
SOFT_NAMES = _words("avalanche cosmos polygon optimism ripple stellar celestia tron sonic pepe floki lido sei sui aptos hedera terra babylon phala monad")
EXTRA_ALIASES = {"ether": "ETH", "xbt": "BTC", "bnb chain": "BNB", "shiba": "SHIB", "dogwifhat": "WIF"}
CONTEXT_AFTER = (
    r"(?:token|tokens|coin|coins|price|prices|holders|perp|perps|perpetual|futures|staking|airdrop|listing|network|mainnet|chain|blockchain"
    r"|protocol|ecosystem|rally|rallies|surges?|jumps?|soars?|plunges?|drops?|falls?|crash(?:es)?|whales?|ETF)"
)
CRYPTO_CONTEXT = re.compile(r"\b(?:crypto|token|coin|blockchain|defi|altcoin|binance|exchange|listing|perpetual|futures|airdrop|staking|mainnet|on-chain|onchain)\b", re.I)


def base_assets(universe: set[str]) -> dict[str, str]:
    """Base asset → perp symbol (1000PEPEUSDT → PEPE); the plain contract wins over a multiplier one."""
    out: dict[str, str] = {}
    for symbol in sorted(universe, key=len, reverse=True):
        if not symbol.endswith("USDT"):
            continue
        base = symbol.removesuffix("USDT")
        for prefix in ("1000000", "1000", "1M"):
            if base.startswith(prefix) and len(base) > len(prefix) and not base[len(prefix)].isdigit():
                base = base.removeprefix(prefix)
                break
        if base:
            out[base] = symbol
    return out


@dataclass
class Linker:
    universe: set[str]
    coins: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.bases = base_assets(self.universe)
        self.names: dict[str, str] = {}
        self.generic_names: set[str] = set()
        seen_symbols: set[str] = set()
        for coin in self.coins:
            ticker = str(coin.get("symbol", "")).upper()
            if ticker not in self.bases or ticker in seen_symbols:
                continue
            seen_symbols.add(ticker)
            for alias in {coin.get("name", ""), *coin.get("aliases", [])}:
                alias = re.sub(r"[\u200b-\u200f\ufeff]", "", alias).strip()
                if len(alias) < 3 or alias.upper() == ticker:
                    continue
                key = alias.lower()
                self.names.setdefault(key, ticker)
                if key in GENERIC_NAMES or (ticker in AMBIGUOUS_TICKERS and key == ticker.lower()):
                    self.generic_names.add(key)
        for alias, ticker in EXTRA_ALIASES.items():
            if ticker in self.bases:
                self.names.setdefault(alias, ticker)
        tickers = sorted(self.bases, key=len, reverse=True)
        self._ticker_re = re.compile(r"(?<![A-Za-z0-9$])(" + "|".join(map(re.escape, tickers)) + r")(?![A-Za-z0-9])") if tickers else None
        names = sorted(self.names, key=len, reverse=True)
        self._name_re = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9])", re.I) if names else None
        self._cashtag_re = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,14})\b")
        self._context_re = re.compile(r"^\s*" + CONTEXT_AFTER + r"\b", re.I)
        self._strong_re = re.compile(r"^\s*(?:token|tokens|coin|coins|protocol)\b", re.I)

    def _ticker_hits(self, text: str) -> list[tuple[int, int, str]]:
        if self._ticker_re is None:
            return []
        hits = []
        for m in self._ticker_re.finditer(text):
            ticker = m.group(1)
            if ticker in ALWAYS_CONTEXT:
                continue
            ambiguous = ticker in AMBIGUOUS_TICKERS or len(ticker) <= 2
            in_parens = text[max(0, m.start() - 1) : m.start()] == "(" and text[m.end() : m.end() + 1] in (")", ",", "/")
            followed = bool(self._context_re.match(text[m.end() : m.end() + 20]))
            pair = text[m.end() : m.end() + 5].upper() in ("/USDT", "-USDT") or text[m.end() : m.end() + 4].upper() == "USDT"
            if in_parens or pair or (not ambiguous and (followed or (len(ticker) >= 3 and not _sentence_caps(text)))):
                hits.append((m.start(), m.end(), ticker))
        return hits

    def _name_hits(self, text: str) -> list[tuple[int, int, str]]:
        if self._name_re is None:
            return []
        hits = []
        for m in self._name_re.finditer(text):
            key = m.group(1).lower()
            ticker = self.names[key]
            if " " not in key and not m.group(1)[0].isupper() and key not in LOWERCASE_OK:
                continue
            if key in self.generic_names:
                followed = bool(self._strong_re.match(text[m.end() : m.end() + 20]))
                ticker_near = re.search(rf"\(\s*\$?{re.escape(ticker)}\s*\)", text[m.end() : m.end() + 12])
                if not (followed or ticker_near) or not m.group(1)[0].isupper():
                    continue
            elif key in SOFT_NAMES and not CRYPTO_CONTEXT.search(text) and not self._context_re.match(text[m.end() : m.end() + 20]):
                hits.append((m.start(), m.end(), "?" + ticker))
                continue
            hits.append((m.start(), m.end(), ticker))
        return hits

    def link(self, text: str | None) -> list[str]:
        """Perp symbols mentioned in `text`, in order of first mention, deduplicated."""
        if not text:
            return []
        hits = [(m.start(), m.end(), m.group(1).upper()) for m in self._cashtag_re.finditer(text) if m.group(1).upper() in self.bases]
        hits += self._ticker_hits(text) + self._name_hits(text)
        confirmed = any(not h[2].startswith("?") for h in hits)
        taken: list[tuple[int, int]] = []
        out: list[str] = []
        for start, end, raw in sorted(hits, key=lambda h: (h[0], -(h[1] - h[0]))):
            if any(start < e and end > s for s, e in taken) or (raw.startswith("?") and not confirmed):
                continue
            taken.append((start, end))
            ticker = raw.lstrip("?")
            symbol = self.bases[ticker]
            if symbol not in out:
                out.append(symbol)
        return out


def _sentence_caps(text: str) -> bool:
    """True for ALL-CAPS headlines, where an uppercase word proves nothing."""
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) > 20 and sum(ch.isupper() for ch in letters) / len(letters) > 0.7


def coins_path() -> Path:
    path = settings.data_dir / "intel"
    path.mkdir(parents=True, exist_ok=True)
    return path / "coingecko_markets.json"


def fetch_coins(pages: int = 4, max_age_s: float = 7 * 86400) -> list[dict]:
    """Top `pages` x 250 coins by market cap from CoinGecko (cached a week): [{id, symbol, name}] in rank order."""
    path = coins_path()
    if path.exists() and time.time() - path.stat().st_mtime < max_age_s:
        return json.loads(path.read_text())
    from trader.intel.sources import HEADERS

    coins: list[dict] = []
    with httpx.Client(timeout=30, headers=HEADERS) as c:
        for page in range(1, pages + 1):
            for attempt in range(4):
                response = c.get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": page})
                if response.status_code != 429:
                    break
                time.sleep(15 * (attempt + 1))
            response.raise_for_status()
            coins += [{"id": c_["id"], "symbol": c_["symbol"], "name": c_["name"]} for c_ in response.json()]
            time.sleep(3)
    path.write_text(json.dumps(coins))
    return coins


def default_linker() -> Linker:
    from trader.services.market_data import perp_universe

    try:
        coins = fetch_coins()
    except httpx.HTTPError:
        coins = json.loads(coins_path().read_text()) if coins_path().exists() else []
    return Linker(perp_universe(), coins)
