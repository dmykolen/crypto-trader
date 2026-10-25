import { ShieldAlert, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { fmt } from "../lib/format"
import type { BotState, SystemInfo } from "../lib/types"

interface Props {
  bot: BotState
  system: SystemInfo
  busy: boolean
  error: string | null
  onConfirm: (phrase: string) => void
  onClose: () => void
}

function Consequences({ bot, system }: { bot: BotState; system: SystemInfo }) {
  const n = system.risk.notice
  const q = system.risk.quant
  if (bot.key === "quant") {
    return (
      <>
        <li>
          Щодня о 00:15 UTC бот приводить рахунок до книги на крос-маржі з плечем {q.leverage}× на біржі. Номінал однієї позиції — до {fmt.pctPlain(100 * q.max_position, 0)} капіталу,
          усіх позицій разом — до {fmt.times(q.max_gross, 1)} капіталу.
        </li>
        <li>Якщо капітал упаде на {fmt.pctPlain(100 * q.kill_drawdown, 0)} від піку, бот закриє всі позиції й зупиниться до вашого рішення.</li>
      </>
    )
  }
  return (
    <>
      <li>
        Кожна угода бере ізольовану маржу до {fmt.pctPlain(100 * n.margin_fraction, 0)} вільного капіталу з плечем за плейбуком (не більше {n.max_leverage}×) і біржовим стопом; одночасно — не
        більше {n.max_open_positions} позицій.
      </li>
      <li>Угоди відкриваються за секунди після анонсу, без додаткового підтвердження.</li>
    </>
  )
}

/** Arming real money: what changes and how much is at risk, the keys it needs, and a phrase typed by hand — like signing a dealing ticket. */
export function LiveArm({ bot, system, busy, error, onConfirm, onClose }: Props) {
  const [phrase, setPhrase] = useState("")
  const dialog = useRef<HTMLDialogElement>(null)
  const stay = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    dialog.current?.showModal()
    if (!system.live_ready) stay.current?.focus()
  }, [system.live_ready])
  const ready = system.live_ready
  const matches = phrase === bot.confirm_phrase
  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      className="m-auto w-[min(580px,calc(100vw-32px))] border-0 bg-paper p-0 text-ink backdrop:bg-black/60"
      aria-labelledby="arm-title"
      aria-describedby="arm-what"
    >
      <div className="h-2.5" style={{ backgroundImage: "repeating-linear-gradient(-45deg, var(--live) 0 7px, transparent 7px 14px)" }} />
      <form
        className="p-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (matches && ready) onConfirm(phrase)
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="arm-title" className="head flex items-center gap-2 text-[1.7rem] font-extrabold text-live">
            <ShieldAlert size={22} aria-hidden /> Реальні гроші: {bot.name}
          </h2>
          <button type="button" className="btn btn-ghost h-7 w-7 justify-center border-rule px-0" onClick={onClose} aria-label="Скасувати">
            <X size={15} aria-hidden />
          </button>
        </div>
        <ul id="arm-what" className="mt-4 list-disc space-y-1.5 pl-5 text-[14px] text-ink-2">
          <li>Паперовий процес бота зупиниться, і він стартує знову з реальними ордерами на Binance USDⓈ-M.</li>
          <Consequences bot={bot} system={system} />
          <li>«Зупинити» зупиняє бота, але відкриті позиції лишаються на біржі, доки ви їх не закриєте.</li>
          {system.testnet && <li>Увімкнено демо-рахунок Binance (BINANCE_TESTNET): ордери не торкаються справжніх коштів.</li>}
        </ul>
        {!ready ? (
          <p id="arm-blocked" className="mt-5 border-l-4 border-loss bg-shade p-3 text-[13.5px]">
            <b className="text-loss">Немає ключів Binance API.</b> Додайте <code className="font-mono text-[12.5px]">BINANCE_API_KEY</code> і{" "}
            <code className="font-mono text-[12.5px]">BINANCE_API_SECRET</code> у файл <code className="font-mono text-[12.5px]">.env</code> (дозволи: читання й ф’ючерсна торгівля, без виведення коштів) і
            перезапустіть сервер.
          </p>
        ) : (
          <label className="mt-5 block text-[13.5px]">
            Щоб підтвердити, введіть <b className="num">{bot.confirm_phrase}</b>
            <input autoFocus className="field mt-2 block w-full text-[15px] tracking-wide" value={phrase} onChange={(e) => setPhrase(e.target.value)} placeholder={bot.confirm_phrase} spellCheck={false} />
          </label>
        )}
        {error && <p className="mt-3 text-[13px] text-loss">{error}</p>}
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button ref={stay} type="button" className="btn btn-ghost" onClick={onClose}>
            Лишити папір
          </button>
          <button type="submit" className="btn btn-live" disabled={!ready || !matches || busy} aria-describedby={ready ? undefined : "arm-blocked"}>
            {busy ? "Перемикаю…" : "Торгувати реальними грошима"}
          </button>
        </div>
      </form>
    </dialog>
  )
}
