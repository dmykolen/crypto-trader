"""Application metrics — add yours here, use them from anywhere (services, jobs, transports).

Rules that keep the dashboards usable:
  * counters `<thing>_total`, durations `<thing>_seconds`;
  * label values stay BOUNDED — event types, sources, modes, exit reasons; never a symbol, a title or an id;
  * a metric exists once its module is imported (transports/http/system.py imports this one).

Per-route HTTP count/latency/size comes from the instrumentator and is NOT defined here.
"""

from importlib.metadata import version

from prometheus_client import Counter, Gauge, Histogram, Info

from trader.core.config import settings

app_info = Info("app", "Service build information")
app_info.info({"service": settings.service_name, "version": version("trader"), "trading_mode": settings.trading_mode})

news_items_total = Counter("news_items_total", "News items ingested", ["source"])
news_events_total = Counter("news_events_total", "Tradable events detected", ["event_type"])
news_poll_seconds = Histogram("news_poll_seconds", "Duration of one news-source poll", ["source"])
llm_calls_total = Counter("llm_calls_total", "Anthropic API calls", ["model", "status"])
orders_total = Counter("orders_total", "Positions opened", ["mode", "side"])
trades_closed_total = Counter("trades_closed_total", "Positions closed", ["mode", "reason"])
open_positions = Gauge("open_positions", "Currently open positions", ["mode"])
notice_latency_seconds = Histogram(
    "notice_latency_seconds", "Delay between a notice's publication and the moment the trader saw it", ["source"], buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 30, 60, 300)
)
