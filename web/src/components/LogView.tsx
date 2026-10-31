import clsx from "clsx"
import { Pause, Play, TriangleAlert } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Pulse } from "./ui"

const LEVEL = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ (\w+) /

export function level(line: string): "error" | "warn" | "info" | "trace" | "detail" {
  const m = LEVEL.exec(line)
  if (m) return m[1] === "ERROR" || m[1] === "CRITICAL" ? "error" : m[1] === "WARNING" ? "warn" : "info"
  if (/^\s/.test(line) || line.startsWith("Traceback")) return "detail"
  return /^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt)\b/.test(line) ? "trace" : "info"
}

export function useLogStream(source: string | null) {
  const [lines, setLines] = useState<string[]>([])
  const [live, setLive] = useState(false)
  useEffect(() => {
    if (!source) return
    setLines([])
    const es = new EventSource(`/api/v1/logs/${encodeURIComponent(source)}/stream`)
    es.onopen = () => setLive(true)
    es.onerror = () => setLive(false)
    es.onmessage = (e) => {
      const d = JSON.parse(e.data) as { lines: string[]; reset?: boolean }
      setLines((prev) => (d.reset ? d.lines : [...prev, ...d.lines]).slice(-3000))
    }
    return () => {
      es.close()
      setLive(false)
    }
  }, [source])
  return { lines, live }
}

export function LogView({ source, errorsOnly, setErrorsOnly }: { source: string | null; errorsOnly: boolean; setErrorsOnly: (v: boolean) => void }) {
  const { lines, live } = useLogStream(source)
  const [paused, setPaused] = useState(false)
  const frozen = useRef<string[]>([])
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  if (!paused) frozen.current = lines
  const shown = errorsOnly ? frozen.current.filter((l) => level(l) === "error" || level(l) === "trace") : frozen.current
  useEffect(() => {
    if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [shown.length, source])
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2 text-[12px]">
        <span className="flex items-center gap-2 text-text-2">
          <Pulse state={live ? "on" : "off"} beat={lines.length} />
          {live ? (paused ? "на паузі" : "наживо") : "підключаюсь…"}
        </span>
        <span className="ml-auto flex gap-1.5">
          <button type="button" onClick={() => setErrorsOnly(!errorsOnly)} className={clsx("btn h-7 px-2.5 text-[12px]", !errorsOnly && "btn-ghost")} aria-pressed={errorsOnly}>
            <TriangleAlert size={13} aria-hidden /> Лише помилки
          </button>
          <button type="button" onClick={() => setPaused(!paused)} className="btn btn-ghost h-7 px-2.5 text-[12px]" aria-pressed={paused}>
            {paused ? <Play size={13} aria-hidden /> : <Pause size={13} aria-hidden />}
            {paused ? "Продовжити" : "Пауза"}
          </button>
        </span>
      </div>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}
        className="min-h-0 flex-1 overflow-auto px-3.5 py-2.5 font-mono text-[11.5px] leading-[1.6]"
        role="log"
        aria-live="off"
      >
        {shown.length ? (
          shown.map((line, i) => {
            const v = level(line)
            return (
              <div key={i} className={clsx("break-all whitespace-pre-wrap", v === "error" && "font-semibold text-text", v === "trace" && "font-medium text-text", v === "warn" && "text-text-2", (v === "info" || v === "detail") && "text-text-3", v === "detail" && "opacity-70")}>
                {v === "error" && "⚠ "}
                {line}
              </div>
            )
          })
        ) : (
          <p className="text-text-3">{errorsOnly ? "Помилок у видимій частині логу немає." : "Лог порожній."}</p>
        )}
      </div>
    </div>
  )
}
