import clsx from "clsx"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"

import { Dot, ErrorNote, Headline, KV } from "../components/Print"
import { api } from "../lib/api"
import { when } from "../lib/format"
import { useBotControl, useOverview } from "../lib/hooks"
import type { BotKey } from "../lib/types"
import { Loading, Page } from "./Overview"

function Logs({ bot }: { bot: BotKey }) {
  const logs = useQuery({ queryKey: ["logs", bot], queryFn: () => api.logs(bot, 400), refetchInterval: 4000 })
  const box = useRef<HTMLPreElement>(null)
  const [follow, setFollow] = useState(true)
  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [logs.data, follow])
  return (
    <div>
      <label className="flex items-center gap-2 pb-1 text-[12.5px] text-ink-2">
        <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Слідкувати за кінцем журналу
      </label>
      {logs.data?.lines.length ? (
        <pre ref={box} className="h-[360px] overflow-auto border border-rule bg-shade p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap" aria-live="off">
          {logs.data.lines.join("\n")}
        </pre>
      ) : (
        <p className="border border-dashed border-rule p-4 text-[13px] text-ink-2">
          Журнал порожній: цього бота запустили не з пульта, тож його вивід іде туди, куди його перенаправили в терміналі. Зупиніть і запустіть бота тут — і журнал з’явиться на цій сторінці.
        </p>
      )}
    </div>
  )
}

export function System() {
  const overview = useOverview()
  const { start, stop } = useBotControl()
  const [bot, setBot] = useState<BotKey>("quant")
  if (overview.isLoading) return <Page>{<Loading what="систему" />}</Page>
  if (!overview.data) return <Page>{<ErrorNote error={overview.error} />}</Page>
  const { bots, system } = overview.data
  return (
    <Page>
      <div className="pt-5">
        <Headline as="h1" title="Система" dek="Процеси ботів, їхні журнали, моделі й режим торгівлі. Сервер слухає лише 127.0.0.1." />
      </div>
      <section className="rule-heavy overflow-x-auto pt-3">
        <table className="agate min-w-[760px]">
          <thead>
            <tr>
              <th>Бот</th>
              <th>Стан</th>
              <th>Режим</th>
              <th className="r">PID</th>
              <th>Працює</th>
              <th>Запущено</th>
              <th>Керування</th>
            </tr>
          </thead>
          <tbody>
            {bots.map((b) => (
              <tr key={b.key}>
                <td className="font-semibold" style={{ color: b.key === "notice" ? "var(--notice)" : "var(--quant)" }}>
                  {b.name}
                </td>
                <td>
                  <span className="inline-flex items-center gap-2">
                    <Dot on={b.running} live={b.mode === "live" && b.running} /> {b.running ? "працює" : "зупинено"}
                  </span>
                </td>
                <td className={clsx(b.mode === "live" && b.running && "font-semibold text-live")}>{b.mode === "live" ? "реальні гроші" : "папір"}</td>
                <td className="r num">{b.pid ?? "—"}</td>
                <td className="num">{when.duration(b.uptime_s)}</td>
                <td>{b.managed ? "з пульта" : b.running ? "з терміналу" : "—"}</td>
                <td>
                  {b.running ? (
                    <button type="button" className="btn btn-ghost h-7" onClick={() => stop.mutate(b.key)} disabled={stop.isPending}>
                      Зупинити
                    </button>
                  ) : (
                    <button type="button" className="btn h-7" onClick={() => start.mutate({ bot: b.key, mode: "paper" })} disabled={start.isPending}>
                      Запустити на папері
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {(start.error || stop.error) && <p className="mt-2 text-[12.5px] text-loss">{((start.error ?? stop.error) as Error).message}</p>}
      </section>
      <section className="rule-heavy mt-8 grid grid-cols-12 gap-x-6 pt-3">
        <div className="col-span-12 lg:col-span-8">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <Headline as="h2" title="Журнал" />
            <div className="flex gap-1 pb-2" role="group" aria-label="Чий журнал">
              {bots.map((b) => (
                <button key={b.key} type="button" aria-pressed={b.key === bot} className={clsx("btn h-7 px-2.5 text-[12.5px]", b.key !== bot && "btn-ghost")} onClick={() => setBot(b.key)}>
                  {b.name}
                </button>
              ))}
            </div>
          </div>
          <Logs bot={bot} />
        </div>
        <div className="col-span-12 lg:col-span-4 lg:colrule lg:pl-6">
          <Headline as="h2" title="Стан" />
          <KV
            rows={[
              ["Ключі Binance API", system.live_ready ? "налаштовані" : <b className="font-semibold text-live">немає — реальна торгівля вимкнена</b>],
              ["Демо-рахунок Binance", system.testnet ? "увімкнено" : "вимкнено"],
              ["Моделі навчені на даних до", system.models_trained_through ? when.day(system.models_trained_through) : "30 вер. 2026"],
              ["Наступне перенавчання", `≈ ${when.day(system.next_retrain_due)}`],
              ["Наступний ребаланс Кванта", when.dateTime(system.next_quant_rebalance)],
            ]}
          />
          <h3 className="head mt-6 text-[1.1rem] font-extrabold">Як увімкнути реальну торгівлю</h3>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-[13px] text-ink-2">
            <li>Створіть ключ API на Binance з дозволами «читання» і «ф’ючерси», без виведення коштів; обмежте його вашою IP-адресою.</li>
            <li>
              Додайте <code className="font-mono text-[12px]">BINANCE_API_KEY</code> і <code className="font-mono text-[12px]">BINANCE_API_SECRET</code> у файл <code className="font-mono text-[12px]">.env</code> (для перевірки спершу{" "}
              <code className="font-mono text-[12px]">BINANCE_TESTNET=true</code>).
            </li>
            <li>
              Перезапустіть <code className="font-mono text-[12px]">trader serve</code> і натисніть «Увімкнути реальні гроші» біля бота.
            </li>
          </ol>
        </div>
      </section>
    </Page>
  )
}
