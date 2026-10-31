import { Command } from "cmdk"
import { FlaskConical, Moon, Palette, Play, Square, Sun, X } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import { useBotControl, useOverview } from "../lib/hooks"
import { SKINS, setEdition, setSkin, useEdition, useSkin } from "../lib/theme"
import type { BotKey } from "../lib/types"
import { NAV } from "./Shell"

export function CommandMenu({ open, setOpen }: { open: boolean; setOpen: (open: boolean) => void }) {
  const navigate = useNavigate()
  const { data } = useOverview()
  const { start, stop } = useBotControl()
  const edition = useEdition()
  const skin = useSkin()
  const [confirm, setConfirm] = useState<BotKey | null>(null)
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen(!open)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [open, setOpen])
  useEffect(() => {
    if (!open) setConfirm(null)
  }, [open])
  const run = (fn: () => void) => {
    fn()
    setOpen(false)
  }
  const bots = data?.bots ?? []
  const target = bots.find((b) => b.key === confirm)
  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Дії пульта" loop>
      <Command.Input placeholder={target ? `Зупинити ${target.name}?` : "Що зробити? Сторінка, бот, тест…"} />
      <Command.List>
        <Command.Empty>Нічого не знайдено.</Command.Empty>
        {target ? (
          <Command.Group heading={`Зупинити ${target.name}?`}>
            <Command.Item value="так зупинити" onSelect={() => run(() => stop.mutate(target.key))}>
              <Square size={15} aria-hidden /> Так, зупинити {target.name}
            </Command.Item>
            <Command.Item value="скасувати" onSelect={() => setConfirm(null)}>
              <X size={15} aria-hidden /> Скасувати
            </Command.Item>
          </Command.Group>
        ) : (
          <>
            <Command.Group heading="Перейти">
              {NAV.map(({ to, label, icon: Icon }) => (
                <Command.Item key={to} value={`перейти ${label}`} onSelect={() => run(() => navigate(to))}>
                  <Icon size={15} aria-hidden /> {label}
                </Command.Item>
              ))}
            </Command.Group>
            <Command.Group heading="Боти">
              {bots.map((b) =>
                b.running ? (
                  <Command.Item key={b.key} value={`зупинити ${b.name}`} onSelect={() => setConfirm(b.key)}>
                    <Square size={15} aria-hidden /> Зупинити {b.name}
                  </Command.Item>
                ) : (
                  <Command.Item key={b.key} value={`запустити ${b.name}`} onSelect={() => run(() => start.mutate({ bot: b.key, mode: "paper" }))}>
                    <Play size={15} aria-hidden /> Запустити {b.name} · віртуальні гроші
                  </Command.Item>
                ),
              )}
            </Command.Group>
            <Command.Group heading="Лабораторія">
              <Command.Item value="новий тест лабораторія" onSelect={() => run(() => navigate("/lab"))}>
                <FlaskConical size={15} aria-hidden /> Новий тест
              </Command.Item>
            </Command.Group>
            <Command.Group heading="Вигляд">
              <Command.Item value="тема світла темна" onSelect={() => run(() => setEdition(edition === "night" ? "day" : "night"))}>
                {edition === "night" ? <Sun size={15} aria-hidden /> : <Moon size={15} aria-hidden />}
                {edition === "night" ? "Світла тема" : "Темна тема"}
              </Command.Item>
              {SKINS.filter((x) => x.key !== skin).map((x) => (
                <Command.Item key={x.key} value={`палітра ${x.label}`} onSelect={() => run(() => setSkin(x.key))}>
                  <Palette size={15} aria-hidden /> Палітра «{x.label}»
                </Command.Item>
              ))}
            </Command.Group>
          </>
        )}
      </Command.List>
    </Command.Dialog>
  )
}
