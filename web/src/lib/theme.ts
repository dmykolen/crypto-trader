import { useSyncExternalStore } from "react"

export type Edition = "day" | "night"

const listeners = new Set<() => void>()

function read(): Edition {
  return document.documentElement.dataset.edition === "night" ? "night" : "day"
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
    /* private mode: the choice lasts for this tab */
  }
  listeners.forEach((fn) => fn())
}

export function useEdition(): Edition {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    read,
    () => "day",
  )
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export const BOT_HUE = { notice: "var(--notice)", quant: "var(--quant)", lab: "var(--lab)" } as const
