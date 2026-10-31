import { useSyncExternalStore } from "react"

export type Edition = "day" | "night"

const listeners = new Set<() => void>()

function read(): Edition {
  return document.documentElement.dataset.edition === "day" ? "day" : "night"
}

/** Switch the whole page at once: transitions are suspended for the swap so no element repaints late in the old edition's ink. */
export function setEdition(edition: Edition): void {
  const root = document.documentElement
  root.classList.add("switching")
  root.dataset.edition = edition
  void root.offsetHeight
  requestAnimationFrame(() => root.classList.remove("switching"))
  try {
    localStorage.setItem("edition", edition)
  } catch {
    return
  }
  listeners.forEach((fn) => fn())
}

export type Skin = "signal" | "mono" | "ember"

export const SKINS: { key: Skin; label: string }[] = [
  { key: "signal", label: "Сигнал" },
  { key: "mono", label: "Моно" },
  { key: "ember", label: "Помаранч" },
]

function readSkin(): Skin {
  const skin = document.documentElement.dataset.skin
  return skin === "mono" || skin === "ember" ? skin : "signal"
}

export function setSkin(skin: Skin): void {
  const root = document.documentElement
  root.classList.add("switching")
  if (skin === "signal") delete root.dataset.skin
  else root.dataset.skin = skin
  void root.offsetHeight
  requestAnimationFrame(() => root.classList.remove("switching"))
  try {
    localStorage.setItem("skin", skin)
  } catch {
    return
  }
  listeners.forEach((fn) => fn())
}

export function useSkin(): Skin {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    readSkin,
    () => "signal",
  )
}

export function useEdition(): Edition {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    read,
    () => "night",
  )
}

let probe: CanvasRenderingContext2D | null = null

function rgba(color: string): [number, number, number, number] {
  probe ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true })
  if (!probe) return [128, 128, 128, 1]
  probe.clearRect(0, 0, 1, 1)
  probe.fillStyle = color
  probe.fillRect(0, 0, 1, 1)
  const [r = 0, g = 0, b = 0, a = 255] = probe.getImageData(0, 0, 1, 1).data
  return [r, g, b, a / 255]
}

export function cssVar(name: string): string {
  const [r, g, b, a] = rgba(getComputedStyle(document.documentElement).getPropertyValue(name).trim())
  return a >= 1 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`
}

export function alpha(color: string, opacity: number): string {
  const [r, g, b] = rgba(color)
  return `rgba(${r}, ${g}, ${b}, ${opacity})`
}
