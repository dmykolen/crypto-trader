import { autoUpdate, flip, offset, shift, useFloating } from "@floating-ui/react-dom"
import clsx from "clsx"
import { ChevronDown, Info, Maximize2, Minimize2, Minus, MoveHorizontal, PanelTop } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { createPortal } from "react-dom"

import { setPanel, usePanel, usePanels } from "../lib/layout"

const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

export function Pulse({ state, beat, label }: { state: "on" | "off" | "down"; beat?: unknown; label?: string }) {
  const [flare, setFlare] = useState(0)
  const seen = useRef(beat)
  useEffect(() => {
    if (seen.current !== beat) {
      seen.current = beat
      setFlare((f) => f + 1)
    }
  }, [beat])
  return (
    <span className="pulse" data-state={state} role={label ? "img" : undefined} aria-label={label}>
      {flare > 0 && state === "on" && <span key={flare} className="flare" aria-hidden />}
    </span>
  )
}

export function Tip({ children, label = "Пояснення", align = "center", side = "top" }: { children: ReactNode; label?: string; align?: "start" | "center" | "end"; side?: "top" | "bottom" }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const { refs, floatingStyles } = useFloating({
    open,
    placement: align === "center" ? side : `${side}-${align}`,
    strategy: "fixed",
    middleware: [offset(8), flip({ padding: 8 }), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })
  return (
    <span className="inline-flex align-middle">
      <button
        ref={refs.setReference}
        type="button"
        aria-describedby={id}
        aria-label={label}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full text-text-3 transition-colors hover:text-text focus-visible:text-text"
      >
        <Info size={13} strokeWidth={2} aria-hidden />
      </button>
      <span id={id} className="sr-only">
        {children}
      </span>
      {open &&
        createPortal(
          <span
            ref={refs.setFloating}
            style={floatingStyles}
            aria-hidden
            className="pointer-events-none z-[70] w-max max-w-[min(300px,calc(100vw-16px))] animate-[fade_150ms_var(--ease-out)] rounded-lg border border-line-strong bg-raised px-3 py-2 text-left text-[12px] leading-snug font-normal tracking-normal text-text-2 normal-case shadow-[0_16px_40px_-12px_rgb(0_0_0/0.55)]"
          >
            {children}
          </span>,
          document.body,
        )}
    </span>
  )
}

export function Odometer({ text, className }: { text: string; className?: string }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setReady(true), 40)
    return () => clearTimeout(id)
  }, [])
  const chars = [...text]
  return (
    <span className={clsx("odo", className)} role="text" aria-label={text}>
      {chars.map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={chars.length - i} className="odo-col" aria-hidden>
            <span className="odo-strip" style={{ transform: `translateY(-${ready ? Number(ch) : 0}em)` }}>
              {DIGITS.map((d) => (
                <span key={d}>{d}</span>
              ))}
            </span>
          </span>
        ) : (
          <span key={`s${chars.length - i}`} aria-hidden>
            {ch}
          </span>
        ),
      )}
    </span>
  )
}

function Control({ label, onClick, children, active }: { label: string; onClick: () => void; children: ReactNode; active?: boolean }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className={clsx("flex h-7 w-7 items-center justify-center rounded-md transition-colors hover:bg-press hover:text-text", active ? "text-text" : "text-text-3")}>
      {children}
    </button>
  )
}

export interface PanelProps {
  id: string
  title: ReactNode
  tip?: ReactNode
  side?: ReactNode
  actions?: ReactNode
  summary?: ReactNode
  children: ReactNode
  className?: string
  wideClass?: string
  foldClass?: string
  bodyClass?: string
  maxBodyClass?: string
  index?: number
}

export function Panel({ id, title, tip, side, actions, summary, children, className, wideClass = "lg:col-span-12", foldClass, bodyClass, maxBodyClass, index = 0 }: PanelProps) {
  const state = usePanel(id)
  useEffect(() => {
    if (!state.max) return
    const close = (e: KeyboardEvent) => e.key === "Escape" && setPanel(id, { max: false })
    document.addEventListener("keydown", close)
    return () => document.removeEventListener("keydown", close)
  }, [id, state.max])
  if (state.dock) return null
  const header = (
    <header className="flex h-11 flex-none items-center justify-between gap-2 pr-2 pl-3">
      <div className="flex min-w-0 items-center gap-2">
        <button type="button" onClick={() => setPanel(id, { fold: !state.fold })} aria-expanded={!state.fold} className="flex min-w-0 items-center gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-raised" title={state.fold ? "Розгорнути" : "Згорнути"}>
          <ChevronDown size={15} className={clsx("flex-none text-text-3 transition-transform duration-200", state.fold && "-rotate-90")} aria-hidden />
          <h2 className="truncate text-[13px] font-semibold">{title}</h2>
        </button>
        {tip && <Tip align="start">{tip}</Tip>}
        {side}
        {state.fold && summary && <span className="ml-1 min-w-0 truncate text-[12.5px] text-text-2">{summary}</span>}
      </div>
      <div className="flex flex-none items-center gap-1">
        {!state.fold && actions}
        <span className="panel-controls flex items-center">
          {!state.max && (
            <span className="hidden lg:contents">
              <Control label={state.wide ? "Звузити" : "На всю ширину"} onClick={() => setPanel(id, { wide: !state.wide })} active={state.wide}>
                <MoveHorizontal size={14} aria-hidden />
              </Control>
            </span>
          )}
          <Control label={state.max ? "Згорнути з повного екрана" : "На весь екран"} onClick={() => setPanel(id, { max: !state.max, fold: false })}>
            {state.max ? <Minimize2 size={14} aria-hidden /> : <Maximize2 size={14} aria-hidden />}
          </Control>
          <Control label="Сховати в кнопку" onClick={() => setPanel(id, { dock: true, max: false })}>
            <Minus size={14} aria-hidden />
          </Control>
        </span>
      </div>
    </header>
  )
  const inline = (
    <section
      className={clsx("panel reveal group/panel flex min-w-0 flex-col", state.wide ? wideClass : className, state.fold && clsx("self-start", foldClass))}
      style={{ "--i": index } as CSSProperties}
      data-panel={id}
    >
      {header}
      {!state.fold && <div className={clsx("min-w-0 flex-1", bodyClass)}>{children}</div>}
    </section>
  )
  return (
    <>
      {state.max ? <section className={clsx("panel min-h-24 opacity-40", state.wide ? wideClass : className)} aria-hidden /> : inline}
      {createPortal(
        <AnimatePresence>
          {state.max && (
            <motion.div key={id} className="fixed inset-0 z-50 flex p-3 md:p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
              <div className="absolute inset-0 bg-bg/80 backdrop-blur-sm" onClick={() => setPanel(id, { max: false })} aria-hidden />
              <motion.section
                className="panel relative flex min-h-0 w-full flex-col"
                initial={{ scale: 0.97, y: 10 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.98, opacity: 0 }}
                transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                role="dialog"
                aria-modal="true"
              >
                {header}
                <div className={clsx("min-h-0 min-w-0 flex-1 overflow-auto", maxBodyClass ?? bodyClass)}>{children}</div>
              </motion.section>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  )
}

export function Dock({ panels }: { panels: { id: string; title: string }[] }) {
  const states = usePanels()
  const docked = panels.filter((p) => states[p.id]?.dock)
  return (
    <AnimatePresence initial={false}>
      {docked.length > 0 && (
        <motion.div className="mb-3 flex flex-wrap items-center gap-2" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }}>
          <PanelTop size={15} className="text-text-3" aria-label="Сховані панелі" />
          {docked.map((p) => (
            <motion.button
              layout
              key={p.id}
              type="button"
              onClick={() => setPanel(p.id, { dock: false })}
              className="flex h-8 items-center gap-2 rounded-full border border-line-strong bg-panel px-3.5 text-[12.5px] font-medium text-text-2 transition-colors hover:border-text-3 hover:text-text"
              title="Показати панель"
            >
              {p.title}
            </motion.button>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function ModeChip({ live }: { live: boolean }) {
  return live ? <span className="chip live-hatch border-live text-live">РЕАЛЬНІ ГРОШІ</span> : <span className="chip">віртуальні</span>
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={clsx("skeleton block", className)} aria-hidden />
}

export function Stat({ label, tip, children, className }: { label: string; tip?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("min-w-0", className)}>
      <div className="flex items-center gap-1.5">
        <span className="label">{label}</span>
        {tip && <Tip align="start">{tip}</Tip>}
      </div>
      <div className="mt-1 text-[15px] font-semibold">{children}</div>
    </div>
  )
}

export function ConfirmButton({ children, confirm, onConfirm, className, disabled, title }: { children: ReactNode; confirm: ReactNode; onConfirm: () => void; className?: string; disabled?: boolean; title?: string }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const id = setTimeout(() => setArmed(false), 3500)
    return () => clearTimeout(id)
  }, [armed])
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      className={clsx("btn h-7 px-2.5 text-[12px]", armed ? "border-text bg-text text-bg" : "btn-ghost", className)}
      onClick={() => {
        if (armed) {
          setArmed(false)
          onConfirm()
        } else setArmed(true)
      }}
    >
      {armed ? confirm : children}
    </button>
  )
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx("relative inline-flex h-6 w-11 flex-none items-center rounded-full border transition-colors duration-200 disabled:opacity-50", checked ? "border-brand bg-brand" : "border-line-strong bg-raised")}
    >
      <span className={clsx("inline-block h-[18px] w-[18px] rounded-full shadow transition-transform duration-200", checked ? "translate-x-[22px] bg-bg" : "translate-x-[2px] bg-text-2")} />
    </button>
  )
}
