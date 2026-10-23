"""Research reports — written to `reports/` as JSON (machine) + Markdown (human)."""

import json
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
from sqlmodel import Session

from trader.ai import analyst
from trader.core.config import settings
from trader.integrations.llm import LLM
from trader.services import playbooks
from trader.services.engine import Costs

log = logging.getLogger(__name__)

VARIANTS = [
    ("baseline", None, 1.0, playbooks.LCB_Z),
    ("entry latency 3 min", 180, 1.0, playbooks.LCB_Z),
    ("entry latency 5 min", 300, 1.0, playbooks.LCB_Z),
    ("2x slippage", None, 2.0, playbooks.LCB_Z),
    ("3x slippage", None, 3.0, playbooks.LCB_Z),
    ("looser selection z=0.5", None, 1.0, 0.5),
    ("stricter selection z=2", None, 1.0, 2.0),
]


def _write(name: str, doc: dict, markdown: str) -> None:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    (settings.reports_dir / f"{name}.json").write_text(json.dumps(doc, indent=2, default=str, ensure_ascii=False) + "\n")
    (settings.reports_dir / f"{name}.md").write_text(markdown.rstrip("\n") + "\n")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def event_study(samples: list[playbooks.Sample]) -> dict[str, dict]:
    """Average path after each event type, from our first possible fill (no strategy, no selection)."""
    marks = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "8h": 480, "23h": 1380}
    by_type = defaultdict(list)
    for s in samples:
        by_type[s.type.value].append(s)
    out = {}
    for etype, group in sorted(by_type.items()):
        rows = defaultdict(list)
        for s in group:
            o, _, _, c = s.ohlc
            pre = c[max(0, int(np.searchsorted(s.open_time, s.ts - 60_000, side="right")) - 1)]
            entry = o[s.base]
            rows["jump_before_fill_pct"].append((entry / pre - 1) * 100)
            for name, m in marks.items():
                rows[f"ret_{name}_pct"].append((c[min(s.base + m, len(c) - 1)] / entry - 1) * 100)
        stats = {
            k: {"mean": round(float(np.mean(v)), 2), "median": round(float(np.median(v)), 2), "pct_up": round(float(np.mean(np.array(v) > 0)) * 100, 1)} for k, v in rows.items()
        }
        out[etype] = {"events": len(group)} | stats
    return out


def _trade_stats(decisions: list[playbooks.Decision]) -> dict:
    """Per-trade view: each OOS trade on a fresh $1000 balance."""
    traded = [d for d in decisions if d.ret is not None]
    rets = np.array([d.ret for d in traded], dtype=float)
    tokens = sorted({d.symbol for d in traded if (d.pnl_on_1000 or 0.0) >= 100})
    return {
        "oos_trades": len(traded),
        "win_rate": round(float((rets > 0).mean()), 3) if len(rets) else None,
        "mean_ret_on_margin": round(float(rets.mean()), 4) if len(rets) else None,
        "median_ret_on_margin": round(float(np.median(rets)), 4) if len(rets) else None,
        "total_pnl_on_1000_each": round(float(rets.sum() * 1000), 2),
        "trades_ge_100_usd_in_24h": int((rets >= 0.1).sum()),
        "liquidations": int((rets <= -0.99).sum()),
        "tokens_ge_100_usd_in_24h": tokens,
    }


def _token_rollup(decisions: list[playbooks.Decision]) -> list[dict]:
    by_symbol = defaultdict(list)
    for d in decisions:
        if d.ret is not None:
            by_symbol[d.symbol].append(d)
    rows = []
    for symbol, ds in by_symbol.items():
        best = max(ds, key=lambda d: d.ret or 0.0)
        rows.append({
            "symbol": symbol,
            "trades": len(ds),
            "total_pnl_on_1000": round(sum(d.pnl_on_1000 or 0.0 for d in ds), 2),
            "best_24h_pnl_on_1000": best.pnl_on_1000,
            "best_event": f"{best.type} @ {best.time}",
            "best_window": f"{best.entry_time} → {best.exit_time}",
        })
    return sorted(rows, key=lambda r: -(r["best_24h_pnl_on_1000"] or 0.0))


def _robustness(samples: list[playbooks.Sample], baseline: playbooks.Outcomes) -> list[dict]:
    """The same walk-forward + account replay under slower entries, worse fills and other selection strictness."""
    cache: dict[tuple, playbooks.Outcomes] = {(None, 1.0): baseline}
    rows = []
    for name, latency, slip_mult, z in VARIANTS:
        key = (latency, slip_mult)
        if key not in cache:
            base = Costs.for_events()
            costs = Costs(fee=base.fee, slip=base.slip * slip_mult, stop_slip=base.stop_slip * slip_mult, mmr=base.mmr)
            cache[key] = playbooks.evaluate(samples, costs=costs, latency_s=latency)
        decisions = playbooks.walk_forward(samples, cache[key], z=z)
        stats = _trade_stats(decisions)
        account = playbooks.replay_account(decisions, "fraction").summary
        rows.append({
            "variant": name,
            "oos_trades": stats["oos_trades"],
            "win_rate": stats["win_rate"],
            "mean_ret_on_margin": stats["mean_ret_on_margin"],
            "tokens_ge_100_on_fresh_1000": len(stats["tokens_ge_100_usd_in_24h"]),
            "account_return_pct": account["return_pct"],
            "account_max_dd_pct": account["max_drawdown_pct"],
            "account_tokens_ge_10pct_in_24h": len(account["tokens_ge_10pct_of_balance"]),
        })
        log.info("robustness %s: %s", name, rows[-1])
    return rows


def _half(iso: str) -> str:
    return f"{iso[:4]}-H{1 if int(iso[5:7]) <= 6 else 2}"


def _periods(decisions: list[playbooks.Decision], account: playbooks.AccountRun) -> list[dict]:
    """Half-year breakdown — shows whether the edge is steady or comes from one regime."""
    rows: dict[str, list[float]] = defaultdict(list)
    for d in decisions:
        if d.ret is not None:
            rows[_half(d.time)].append(d.ret)
    equity = 1000.0
    out = []
    for half in sorted(rows):
        start = equity
        equity = next((e for day, e in reversed(account.daily.items()) if _half(day) == half), equity)
        rets = np.array(rows[half])
        out.append({
            "period": half,
            "oos_trades": len(rets),
            "win_rate": round(float((rets > 0).mean()), 3),
            "mean_ret_on_margin": round(float(rets.mean()), 4),
            "account_equity_end": round(equity, 2),
            "account_period_return_pct": round((equity / start - 1) * 100, 2),
        })
    return out


def _concentration(decisions: list[playbooks.Decision]) -> list[dict]:
    """Does the result survive without its best announcements, best trades or best half-year? (live sizing)"""
    traded = [d for d in decisions if d.ret is not None]
    by_notice: dict[str, float] = defaultdict(float)
    by_half: dict[str, float] = defaultdict(float)
    for d in traded:
        by_notice[d.notice] += d.ret or 0.0
        by_half[_half(d.time)] += d.ret or 0.0
    ranked = sorted(by_notice, key=lambda k: -by_notice[k])
    best_half = max(by_half, key=lambda k: by_half[k])
    top_trades = {id(d) for d in sorted(traded, key=lambda d: -(d.ret or 0.0))[:10]}
    variants: list[tuple[str, list[playbooks.Decision]]] = [("all OOS trades", traded)]
    variants += [(f"without the best {k} announcement(s)", [d for d in traded if d.notice not in ranked[:k]]) for k in (1, 2, 5, 10)]
    variants += [("without the best 10 trades", [d for d in traded if id(d) not in top_trades])]
    variants += [(f"without the best half-year ({best_half})", [d for d in traded if _half(d.time) != best_half])]
    rows = []
    for name, kept in variants:
        stats = _trade_stats(kept)
        account = playbooks.replay_account(kept, "fraction").summary
        rows.append({
            "variant": name,
            "oos_trades": stats["oos_trades"],
            "mean_ret_on_margin": stats["mean_ret_on_margin"],
            "tokens_ge_100_on_fresh_1000": len(stats["tokens_ge_100_usd_in_24h"]),
            "account_return_pct": account["return_pct"],
            "account_max_dd_pct": account["max_drawdown_pct"],
            "account_tokens_ge_10pct_in_24h": len(account["tokens_ge_10pct_of_balance"]),
        })
    return rows


def _cluster_bootstrap(decisions: list[playbooks.Decision], n_boot: int = 5000, seed: int = 7) -> dict[str, dict]:
    """Mean return on margin with announcements resampled as whole clusters (trades of one notice move together)."""
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for d in decisions:
        if d.ret is not None:
            groups["all"][d.notice].append(d.ret)
            groups[d.type][d.notice].append(d.ret)
    rng = np.random.default_rng(seed)
    out = {}
    for name, clusters in sorted(groups.items(), key=lambda kv: (kv[0] != "all", kv[0])):
        sums = np.array([sum(v) for v in clusters.values()])
        counts = np.array([len(v) for v in clusters.values()])
        pick = rng.integers(0, len(sums), size=(n_boot, len(sums)))
        means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
        lo, hi = np.percentile(means, [5, 95])
        out[name] = {
            "announcements": len(sums),
            "trades": int(counts.sum()),
            "mean_ret_on_margin": round(float(sums.sum() / counts.sum()), 4),
            "ci90": [round(float(lo), 4), round(float(hi), 4)],
            "p_mean_le_0": round(float((means <= 0).mean()), 4),
        }
    return out


def event_research(session: Session, robustness: bool = True) -> dict:
    """Load every past event, score the playbook grid, walk forward, replay one account, fit live playbooks, write the report."""
    samples = playbooks.load_samples(session)
    outcomes = playbooks.evaluate(samples)
    decisions = playbooks.walk_forward(samples, outcomes)
    fitted = playbooks.fit(samples, outcomes.r)
    playbooks.save_playbooks(fitted)

    stats = _trade_stats(decisions)
    per_type = {}
    for etype in sorted({d.type for d in decisions}):
        of_type = [d for d in decisions if d.type == etype]
        per_type[etype] = {"events": len(of_type)} | {k: v for k, v in _trade_stats(of_type).items() if k != "tokens_ge_100_usd_in_24h"}
    accounts = {p: playbooks.replay_account(decisions, p) for p in ("fraction", "all_in")}
    live = accounts["fraction"].summary
    concentration = _concentration(decisions)
    headline = {
        "generated_at": _now(),
        "assumptions": {
            "entry_latency_s": settings.entry_latency_s,
            "taker_fee": settings.taker_fee,
            "slippage_per_side": settings.event_slippage,
            "stop_slippage_per_side": settings.event_slippage * settings.stop_slippage_mult,
            "maintenance_margin": settings.maintenance_margin,
            "fills": "1m bars; entry at the bar open after the delay; a stop that gaps fills at the open; take-profit never better than its level; "
            "stop/liquidation before take-profit inside a bar",
            "funding": "every historical settlement inside the holding window is charged on the position notional (shorts pay negative rates)",
            "selection": f"walk-forward, LCB(z={playbooks.LCB_Z}) of log-growth, ≥{playbooks.MIN_HISTORY} prior events with known 24h outcomes",
            "risk_rule": f"stops always fire before liquidation (stop ≤ {playbooks.STOP_BEFORE_LIQ:.0%} of the liquidation distance)",
            "sizing": f"per-trade view: a fresh $1000 balance as isolated margin; account view: {settings.margin_fraction:.0%} of equity per trade, "
            f"≤{settings.max_open_positions} open, ≤{settings.max_notice_fraction:.0%} per announcement (the live trader's rules)",
        },
        "events_with_perp_window": len(samples),
        **{k: v for k, v in stats.items() if k != "tokens_ge_100_usd_in_24h"},
        "distinct_tokens_ge_100_usd_in_24h": len(stats["tokens_ge_100_usd_in_24h"]),
        "tokens_ge_100_usd_in_24h": stats["tokens_ge_100_usd_in_24h"],
        "account_tokens_ge_100_per_1000_in_24h": live["tokens_ge_10pct_of_balance"],
        "criterion_met": len(stats["tokens_ge_100_usd_in_24h"]) >= 3 and len(live["tokens_ge_10pct_of_balance"]) >= 3 and live["return_pct"] > 0,
        "criterion_met_without_best_5_announcements": next(
            r["tokens_ge_100_on_fresh_1000"] >= 3 and r["account_tokens_ge_10pct_in_24h"] >= 3 and r["account_return_pct"] > 0
            for r in concentration
            if "best 5 announcement" in r["variant"]
        ),
        "per_type": per_type,
    }
    doc = {
        "headline": headline,
        "accounts": {p: a.summary | {"daily_equity": a.daily, "trades": a.trades} for p, a in accounts.items()},
        "periods": _periods(decisions, accounts["fraction"]),
        "concentration": concentration,
        "clustered_bootstrap": _cluster_bootstrap(decisions),
        "robustness": _robustness(samples, outcomes) if robustness else [],
        "event_study": event_study(samples),
        "live_playbooks": fitted,
        "tokens": _token_rollup(decisions),
        "decisions": [asdict(d) for d in decisions],
    }
    _write("event_research", doc, _event_markdown(doc))
    return doc


def _table(header: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows)]


def _event_markdown(doc: dict) -> str:
    h = doc["headline"]
    acc = doc["accounts"]
    live = acc["fraction"]
    big = [t for t in live["trades"] if t["pnl"] >= 0.1 * t["equity_at_entry"]]
    lines = [
        "# Event-driven playbooks — out-of-sample report",
        "",
        f"Generated {h['generated_at']}. Every trade below was chosen by a rule that saw only events whose 24h outcome",
        "was known before the notice appeared (walk-forward). Costs: taker fee, slippage, stop slippage, funding, isolated",
        "liquidation with maintenance margin — see `assumptions`.",
        "",
        "## Criterion: ≥ $100 within 24h from a $1000 balance, on ≥ 3 tokens",
        "",
        f"* **Per trade** (each OOS trade on a fresh $1000, closed ≤ 24h after the notice): **{h['trades_ge_100_usd_in_24h']}** trades made ≥ $100 "
        f"on **{h['distinct_tokens_ge_100_usd_in_24h']}** distinct tokens.",
        f"* **One account** ($1000 start, {settings.margin_fraction:.0%} of equity per trade, ≤ {settings.max_open_positions} open, "
        f"≤ {settings.max_notice_fraction:.0%} per announcement): ends at **${live['final_equity']:,}** ({live['return_pct']:+}%, "
        f"max drawdown {live['max_drawdown_pct']}%); **{len(big)}** trades made ≥ 10% of the balance within 24h on "
        f"**{len(h['account_tokens_ge_100_per_1000_in_24h'])}** tokens.",
        f"* Criterion met (both views, account profitable overall): **{h['criterion_met']}**; "
        f"still met without the 5 most profitable announcements: **{h['criterion_met_without_best_5_announcements']}**",
        "",
        "## Headline",
        "",
        f"* events with a tradable perpetual window: **{h['events_with_perp_window']}**",
        f"* out-of-sample trades: **{h['oos_trades']}**, win rate **{h['win_rate']}**, mean / median return on margin **{h['mean_ret_on_margin']} / {h['median_ret_on_margin']}**",
        f"* liquidations: **{h['liquidations']}**",
        "",
        "```json",
        json.dumps(h["assumptions"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## One account, two sizing policies",
        "",
        "Overlapping signals share the balance: a signal is skipped while its symbol is open or no margin is free. `all_in` commits",
        "the whole free balance to every trade — shown only to make the point that it is ruinous even with a positive edge.",
        "",
    ]
    keys = [
        "final_equity",
        "return_pct",
        "max_drawdown_pct",
        "trades_taken",
        "signals_skipped",
        "win_rate",
        "trading_days",
        "days_ge_10pct",
        "days_le_minus_10pct",
        "best_day_pct",
        "worst_day_pct",
    ]
    lines += _table(["policy", *keys], [[p, *(a[k] for k in keys)] for p, a in acc.items()])
    lines += ["", "## By half-year (is the edge steady?)", ""]
    pkeys = ["oos_trades", "win_rate", "mean_ret_on_margin", "account_equity_end", "account_period_return_pct"]
    lines += _table(["period", *pkeys], [[r["period"], *(r[k] for k in pkeys)] for r in doc["periods"]])
    lines += ["", "## Concentration (the account without its best announcements / trades / half-year)", ""]
    ckeys = [k for k in doc["concentration"][0] if k != "variant"]
    lines += _table(["variant", *ckeys], [[r["variant"], *(r[k] for k in ckeys)] for r in doc["concentration"]])
    lines += [
        "",
        "## Mean return on margin, announcements resampled as clusters (bootstrap, 90% interval)",
        "",
        "Trades triggered by one notice move together, so the notice — not the trade — is the independent unit.",
        "",
    ]
    lines += _table(
        ["group", "announcements", "trades", "mean", "90% interval", "P(mean ≤ 0)"],
        [[g, v["announcements"], v["trades"], v["mean_ret_on_margin"], f"{v['ci90'][0]} … {v['ci90'][1]}", v["p_mean_le_0"]] for g, v in doc["clustered_bootstrap"].items()],
    )
    if doc["robustness"]:
        lines += ["", "## Robustness (same walk-forward and account, harsher assumptions)", ""]
        rkeys = [k for k in doc["robustness"][0] if k != "variant"]
        lines += _table(["variant", *rkeys], [[r["variant"], *(r[k] for k in rkeys)] for r in doc["robustness"]])
    lines += ["", "## Per event type (out-of-sample, each trade on a fresh $1000)", ""]
    tkeys = ["events", "oos_trades", "win_rate", "mean_ret_on_margin", "total_pnl_on_1000_each", "trades_ge_100_usd_in_24h", "liquidations"]
    lines += _table(["type", *tkeys], [[t, *(v[k] for k in tkeys)] for t, v in h["per_type"].items()])
    lines += ["", "## Live playbooks (fitted on all history with the same rule)", ""]
    lines += _table(
        ["type", "playbook", "events", "mean R", "win rate", "worst R"],
        [[t, v.get("describe", "skip — no positive edge"), v["events"], v.get("mean_ret"), v.get("win_rate"), v.get("worst_ret")] for t, v in doc["live_playbooks"].items()],
    )
    lines += ["", "## Event study (average path after the first possible fill, mean / median)", ""]
    marks = ("jump_before_fill_pct", "ret_1h_pct", "ret_4h_pct", "ret_8h_pct", "ret_23h_pct")
    lines += _table(
        ["type", "n", "jump before fill", "1h", "4h", "8h", "23h"],
        [[t, v["events"], *(f"{v[k]['mean']:+.2f}% / {v[k]['median']:+.2f}%" for k in marks)] for t, v in doc["event_study"].items()],
    )
    lines += ["", "## Account trades that made ≥ 10% of the balance within 24h (≥ $100 per $1000)", ""]
    lines += _table(
        ["entry (UTC)", "exit (UTC)", "symbol", "event", "balance at entry", "margin", "PnL", "return on margin"],
        [[t["entry_time"], t["exit_time"], t["symbol"], t["type"], t["equity_at_entry"], t["margin"], f"{t['pnl']:+.2f}", f"{t['ret']:+.3f}"] for t in big],
    )
    lines += ["", "## Every out-of-sample trade (each on a fresh $1000)", ""]
    lines += _table(
        ["announced (UTC)", "type", "symbol", "playbook", "entry → exit", "R", "PnL on $1000"],
        [
            [
                d["time"],
                d["type"],
                d["symbol"],
                playbooks.Playbook(**d["playbook"]).describe(),
                f"{d['entry_time']} → {d['exit_time']}",
                f"{d['ret']:+.3f}",
                f"{d['pnl_on_1000']:+.2f}",
            ]
            for d in doc["decisions"]
            if d["ret"] is not None
        ],
    )
    return "\n".join(lines) + "\n"


def strategy_research(symbols: list[str], *, days: int, interval: str, train_days: int, fold_days: int) -> dict:
    """Walk-forward strategy selection for each symbol → reports/strategy_selection.*"""
    from trader.services import selection

    start, end = selection.default_window(days, train_days)
    studies = {}
    for symbol in symbols:
        log.info("strategy study %s %s → %s", symbol, start.date(), end.date())
        st = selection.study(symbol, start, end, interval=interval, train_days=train_days, fold_days=fold_days)
        studies[symbol] = {"oos": st.oos.metrics, "current": st.current, "regime": st.regime, "folds": st.folds}
    summary = {
        s: {
            "oos_return_pct": v["oos"]["return_pct"],
            "max_drawdown_pct": v["oos"]["max_drawdown_pct"],
            "sharpe_daily": v["oos"]["sharpe_daily"],
            "best_day_pnl": v["oos"]["best_day_pnl"],
            "worst_day_pnl": v["oos"]["worst_day_pnl"],
            "days_pnl_ge_100": v["oos"]["days_pnl_ge_100_per_1000"],
            "days": v["oos"]["days"],
            "live_choice": v["current"]["describe"] if v["current"]["tradable"] else "flat — no spec with a positive edge",
        }
        for s, v in studies.items()
    }
    protocol = (
        f"Every {fold_days} days the selector picks — among trend / breakout / mean-reversion / ML-forecast strategies × parameters × "
        f"leverage 2-10x × ATR stop/take-profit — the spec with the best lower confidence bound of daily log-growth over the previous "
        f"{train_days} days (flat when no bound is positive); that spec trades the next fold. The folds are replayed as one $1000 account "
        f"({interval} bars, fees, slippage, funding, isolated liquidation), so the equity is entirely out-of-sample."
    )
    window = {"start": start.isoformat(), "end": end.isoformat(), "interval": interval, "train_days": train_days, "fold_days": fold_days}
    doc = {"generated_at": _now(), "window": window, "protocol": protocol, "summary": summary, "symbols": studies}
    lines = ["# Per-token strategy selection — out-of-sample (walk-forward)", "", protocol, ""]
    skeys = ["oos_return_pct", "max_drawdown_pct", "sharpe_daily", "best_day_pnl", "worst_day_pnl", "days_pnl_ge_100", "days", "live_choice"]
    lines += _table(["symbol", *skeys], [[s, *(v[k] for k in skeys)] for s, v in summary.items()])
    for s, v in studies.items():
        lines += ["", f"## {s}", "", f"Regime now: `{json.dumps(v['regime'])}`", ""]
        lines += _table(["fold", "spec chosen on the previous window", "fold return"], [[f"{f['from']} → {f['to']}", f["spec"], f"{f['fold_return_pct']}%"] for f in v["folds"]])
    _write("strategy_selection", doc, "\n".join(lines) + "\n")
    return doc


async def review(llm: LLM, name: str = "event_research") -> dict:
    """Claude's sceptical review of a research report → reports/{name}_review.*"""
    doc = json.loads((settings.reports_dir / f"{name}.json").read_text())
    digest = {k: v for k, v in doc.items() if k not in ("decisions", "symbols", "accounts")}
    if "accounts" in doc:
        digest["accounts"] = {p: {k: v for k, v in a.items() if k not in ("trades", "daily_equity")} for p, a in doc["accounts"].items()}
    if "decisions" in doc:
        digest["latest_oos_trades"] = [d for d in doc["decisions"] if d["ret"] is not None][-80:]
    if "symbols" in doc:
        digest["recent_folds"] = {s: v["folds"][-12:] for s, v in doc["symbols"].items()}
    result = (await analyst.review_strategy(llm, digest)).model_dump()
    lines = [f"# Claude review of `{name}`", "", f"**Verdict: {result['verdict']}**", "", result["summary"], ""]
    for key in ("strengths", "weaknesses", "failure_modes", "suggested_tests"):
        lines += [f"## {key.replace('_', ' ').capitalize()}", "", *(f"* {x}" for x in result[key]), ""]
    _write(f"{name}_review", result | {"generated_at": _now()}, "\n".join(lines))
    return result
