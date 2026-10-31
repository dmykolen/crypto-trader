import { useSyncExternalStore } from "react"

export interface PanelState {
  fold: boolean
  dock: boolean
  wide: boolean
  max: boolean
}

export interface ChromeState {
  compactBar: boolean
  compactRail: boolean
}

const EMPTY: PanelState = { fold: false, dock: false, wide: false, max: false }
const KEY = "layout:v1"
const listeners = new Set<() => void>()

type Store = { panels: Record<string, PanelState>; chrome: ChromeState }

function load(): Store {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Store>
    return { panels: raw.panels ?? {}, chrome: { compactBar: false, compactRail: false, ...raw.chrome } }
  } catch {
    return { panels: {}, chrome: { compactBar: false, compactRail: false } }
  }
}

let store = load()

function save(next: Store) {
  store = next
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...next, panels: Object.fromEntries(Object.entries(next.panels).map(([k, v]) => [k, { ...v, max: false }])) }))
  } catch {
    return
  }
  listeners.forEach((fn) => fn())
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function setPanel(id: string, patch: Partial<PanelState>) {
  const panels = patch.max ? Object.fromEntries(Object.entries(store.panels).map(([k, v]) => [k, { ...v, max: false }])) : { ...store.panels }
  panels[id] = { ...(store.panels[id] ?? EMPTY), ...patch }
  save({ ...store, panels })
}

export function usePanel(id: string): PanelState {
  return useSyncExternalStore(subscribe, () => store.panels[id] ?? EMPTY, () => EMPTY)
}

export function useChrome(): ChromeState {
  return useSyncExternalStore(subscribe, () => store.chrome, () => store.chrome)
}

export function setChrome(patch: Partial<ChromeState>) {
  save({ ...store, chrome: { ...store.chrome, ...patch } })
}

export function usePanels(): Record<string, PanelState> {
  return useSyncExternalStore(subscribe, () => store.panels, () => store.panels)
}
