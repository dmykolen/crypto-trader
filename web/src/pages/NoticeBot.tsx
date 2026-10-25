import clsx from "clsx"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { BotColumn } from "../components/BotColumn"
import { Empty, ErrorNote, Headline, KV, Signed } from "../components/Print"
import { api } from "../lib/api"
import { eventLabel, exitReason, fmt, playbookText, triggerParts, when } from "../lib/format"
import { useCreateJob, useFreshKeys, useOverview } from "../lib/hooks"
import { Loading, Page } from "./Overview"

interface FastPlaybook {
  events: number
  score: number
  oos_trades: number
  oos_mean_ret: number | null
  describe?: string
  playbook?: Record<string, number> | null
}

function Playbooks() {
  const summary = useQuery({ queryKey: ["notice-summary"], queryFn: () => fetch("/api/v1/notice/summary").then((r) => r.json()), staleTime: 60_000 })
  const buckets: Record<string, Record<string, FastPlaybook>> = summary.data?.fast_playbooks?.by_latency ?? {}
  const latencies = Object.keys(buckets).sort((a, b) => Number(a) - Number(b))
  const [picked, setPicked] = useState<string | null>(null)
  const active = picked && buckets[picked] ? picked : (latencies.find((l) => Number(l) === 1) ?? latencies[0] ?? "")
  const rows = Object.entries(buckets[active] ?? {}).sort(([, a], [, b]) => Number(!!b.playbook) - Number(!!a.playbook) || (b.oos_mean_ret ?? -Infinity) - (a.oos_mean_ret ?? -Infinity))
  if (summary.isLoading) return <p className="py-4 text-ink-3">Завантажую плейбуки…</p>
  if (!latencies.length) return <Empty>Плейбуки ще не навчені: потрібен `trader research ticks`.</Empty>
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1 pb-2" role="group" aria-label="Затримка входу">
        <span className="mr-2 text-[12.5px] text-ink-2">Бот бачить анонс через:</span>
        {latencies.map((l) => (
          <button key={l} type="button" onClick={() => setPicked(l)} aria-pressed={l === active} className={clsx("btn h-7 px-2.5 text-[12.5px]", l !== active && "btn-ghost border-rule")}>
            {l.replace(".", ",")} с
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="agate min-w-[620px]">
          <thead>
            <tr>
              <th>Подія</th>
              <th>Що робить бот</th>
              <th className="r">Подій</th>
              <th className="r">Угод поза вибіркою</th>
              <th className="r">Середнє на угоду</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([type, pb]) => (
              <tr key={type} className={pb.playbook ? undefined : "text-ink-3"}>
                <td>{eventLabel(type)}</td>
                <td>{pb.playbook ? playbookText(pb.describe) : "не торгує: немає плейбука з надійною перевагою"}</td>
                <td className="r num">{pb.events}</td>
                <td className="r num">{pb.oos_trades}</td>
                <td className="r">
                  {pb.oos_trades && pb.oos_mean_ret != null ? (
                    <Signed value={100 * pb.oos_mean_ret} digits={1}>
                      {fmt.pct(100 * pb.oos_mean_ret, 1)}
                    </Signed>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-ink-3">
        Середнє — на маржу з урахуванням плеча, витрат і песимістичного виконання, лише угоди поза вибіркою, на якій обирали плейбук. Плейбук вмикається, тільки коли нижня межа довіри до переваги вища за нуль, тому подія з
        додатним середнім на кількох угодах може не торгуватися.
      </p>
    </div>
  )
}

function Replay() {
  const create = useCreateJob()
  const navigate = useNavigate()
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
  const [day, setDay] = useState(yesterday)
  const [days, setDays] = useState(1)
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate({ kind: "notice_replay", params: { day, days } }, { onSuccess: (job) => navigate(`/lab/${job.id}`) })
      }}
    >
      <label className="text-[12.5px] text-ink-2">
        З дня (UTC)
        <input type="date" className="field mt-1 block" value={day} max={yesterday} onChange={(e) => setDay(e.target.value)} required />
      </label>
      <label className="text-[12.5px] text-ink-2">
        Днів
        <input type="number" className="field mt-1 block w-20" min={1} max={90} value={days} onChange={(e) => setDays(Number(e.target.value))} />
      </label>
      <button type="submit" className="btn" disabled={create.isPending}>
        {create.isPending ? "Ставлю в чергу…" : "Прогнати реплей"}
      </button>
      {create.error && <span className="text-[12.5px] text-loss">{(create.error as Error).message}</span>}
    </form>
  )
}

export function NoticeBot() {
  const overview = useOverview()
  const feed = useQuery({ queryKey: ["notice-feed"], queryFn: () => api.noticeFeed(80), refetchInterval: 10_000 })
  const trades = useQuery({ queryKey: ["trades"], queryFn: () => api.trades(200), refetchInterval: 15_000 })
  const fresh = useFreshKeys((feed.data ?? []).map((n) => n.id))
  if (overview.isLoading) return <Page>{<Loading />}</Page>
  if (!overview.data) return <Page>{<ErrorNote error={overview.error} />}</Page>
  const bot = overview.data.bots.find((b) => b.key === "notice")
  const paper = overview.data.paper.notice
  return (
    <Page>
      <div className="pt-5">
        <Headline
          as="h1"
          title="Анонси"
          hue="var(--notice)"
          dek="Читає анонси Binance і Upbit — лістинги, делістинги, теги моніторингу, попередження — і торгує ф’ючерс токена. Плейбук для кожного типу події обраний поза вибіркою для своєї затримки входу."
        />
      </div>
      <div className="rule-heavy grid grid-cols-12 gap-x-6 pt-4">
        <div className="col-span-12 lg:col-span-4">
          {bot && (
            <BotColumn
              bot={bot}
              system={overview.data.system}
              dek=""
              compact
              heading={false}
              figures={
                <KV
                  rows={[
                    ["Угод на папері", paper.trades],
                    ["Відкрито зараз", paper.open],
                    ["Реалізований P&L", <Signed value={paper.realized_pnl}>{fmt.pnl(paper.realized_pnl)}</Signed>],
                    ["Влучність", paper.win_rate_pct == null ? "—" : fmt.pctPlain(paper.win_rate_pct)],
                    ["Анонси Binance", overview.data.system.live_ready ? "WebSocket" : "опитування — WebSocket чекає ключ"],
                    ["Анонси Upbit", "опитування ~1 с"],
                  ]}
                />
              }
            />
          )}
        </div>
        <div className="col-span-12 lg:col-span-8 lg:colrule lg:pl-6">
          <Headline as="h2" title="Плейбуки" dek="Що бот робить на кожен тип анонсу — залежить від того, як швидко він встигає увійти." />
          <Playbooks />
        </div>
      </div>
      <section className="rule-heavy mt-8 pt-3">
        <Headline as="h2" title="Анонси в журналі" dek="Час публікації, тип події та затримка, з якою бот побачив анонс." />
        {feed.data?.length ? (
          <div className="overflow-x-auto">
            <table className="agate min-w-[760px]">
              <thead>
                <tr>
                  <th>Опубліковано</th>
                  <th>Біржа</th>
                  <th>Заголовок</th>
                  <th>Подія</th>
                  <th className="r">Побачено через</th>
                </tr>
              </thead>
              <tbody>
                {feed.data.map((n) => (
                  <tr key={n.id} className={fresh.has(n.id) ? "wet" : undefined} style={{ ["--wet" as string]: "var(--notice)" }}>
                    <td className="num whitespace-nowrap">{when.dateTime(n.published_at)}</td>
                    <td className="capitalize">{n.source}</td>
                    <td>{n.url ? <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a> : n.title}</td>
                    <td>{n.events.length ? n.events.map((e) => [eventLabel(e.type), e.symbols.map((x) => x.replace(/USDT$/, "")).join(", ")].filter(Boolean).join(": ")).join("; ") : <span className="text-ink-3">без торгової події</span>}</td>
                    <td className="r num">{n.latency_s < 120 ? `${n.latency_s.toFixed(1).replace(".", ",")} с` : when.duration(n.latency_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>Анонсів у журналі ще немає.</Empty>
        )}
      </section>
      <section className="rule-heavy mt-8 grid grid-cols-12 gap-x-6 pt-3">
        <div className="col-span-12 overflow-x-auto lg:col-span-8">
          <Headline as="h3" title="Угоди" />
          {trades.data?.length ? (
            <table className="agate min-w-[640px]">
              <thead>
                <tr>
                  <th>Вхід</th>
                  <th>Режим</th>
                  <th>Токен</th>
                  <th>Бік</th>
                  <th>Подія</th>
                  <th className="r">Плече</th>
                  <th>Стан</th>
                  <th className="r">P&L</th>
                </tr>
              </thead>
              <tbody>
                {trades.data.map((t) => (
                  <tr key={t.id}>
                    <td className="num">{when.dateTime(t.entry_time)}</td>
                    <td>{t.mode === "live" ? <b className="text-live">реальні</b> : "папір"}</td>
                    <td className="font-semibold">{t.symbol.replace(/USDT$/, "")}</td>
                    <td>{t.side > 0 ? "лонг" : "шорт"}</td>
                    <td title={triggerParts(t.trigger).playbook}>{triggerParts(t.trigger).event}</td>
                    <td className="r num">{t.leverage}×</td>
                    <td>{t.status === "open" ? "відкрита" : exitReason(t.exit_reason) || "закрита"}</td>
                    <td className="r">
                      <Signed value={t.pnl} arrow={false}>
                        {fmt.pnl(t.pnl)}
                      </Signed>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>Угод ще не було: бот чекає анонсу, для якого є перевірений плейбук, і входить лише в межах його вікна затримки.</Empty>
          )}
        </div>
        <div className="col-span-12 lg:col-span-4 lg:colrule lg:pl-6">
          <Headline as="h3" title="Реплей днів" dek="Справжній торговий цикл на історичних тиках: кожен анонс, ордер і вихід, плейбуки навчені лише на попередніх подіях." />
          <Replay />
        </div>
      </section>
    </Page>
  )
}
