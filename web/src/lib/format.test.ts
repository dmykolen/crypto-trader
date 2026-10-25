import { describe, expect, it } from "vitest"

import { describeEvent, fmt, playbookText, plural, tone, triggerParts } from "./format"

const MINUS = "\u2212"

describe("signed figures", () => {
  it("never prints a negative zero, and color follows the printed digits", () => {
    expect(fmt.weight(-0.0000001)).toBe("0,00 %")
    expect(fmt.pct(-0.004)).toBe("0,00 %")
    expect(fmt.pnl(-0.001)).toBe("$0,00")
    expect(tone(-0.004)).toBe("flat")
    expect(tone(-0.004, 4)).toBe("loss")
  })

  it("uses a true minus sign and an explicit plus", () => {
    expect(fmt.pnl(-10.93)).toBe(`${MINUS}$10,93`)
    expect(fmt.pct(13.2, 1)).toBe("+13,2 %")
    expect(fmt.times(1.93)).toBe("1,93×")
  })
})

describe("prices", () => {
  it("print with the precision of their magnitude, and a row shares its entry's precision", () => {
    expect(fmt.price(80531)).toBe("80 531,0")
    expect(fmt.price(742.62)).toBe("742,62")
    expect(fmt.price(101.65)).toBe("101,65")
    expect(fmt.price(2.5)).toBe("2,500")
    expect(fmt.price(0.004512759)).toBe("0,004513")
    expect(fmt.price(99.5, 102.3)).toBe("99,50")
  })
})

describe("Ukrainian plurals", () => {
  it("picks one / few / many forms", () => {
    expect(plural(1, "лонг", "лонги", "лонгів")).toBe("1 лонг")
    expect(plural(3, "лонг", "лонги", "лонгів")).toBe("3 лонги")
    expect(plural(30, "лонг", "лонги", "лонгів")).toBe("30 лонгів")
    expect(plural(11, "лонг", "лонги", "лонгів")).toBe("11 лонгів")
    expect(plural(21, "лонг", "лонги", "лонгів")).toBe("21 лонг")
  })
})

describe("playbook shorthand", () => {
  it("reads the fast tick playbook", () => {
    expect(playbookText("SHORT 10x hold 600s SL 5% TP 10%")).toBe("шорт 10× тримати 10 хв стоп 5 % тейк 10 %")
  })

  it("reads the slow playbook with entry delay and trail", () => {
    expect(playbookText("LONG 1x, enter +60m, hold ≤480m, SL 10%, TP 10%, trail 5%")).toBe("лонг 1×, вхід через 60 хв, тримати до 8 год, стоп 10 %, тейк 10 %, трейл 5 %")
  })

  it("splits a trade trigger into its event and playbook", () => {
    expect(triggerParts("upbit_caution: LONG 1x, enter +60m, hold ≤480m")).toEqual({ event: "Застереження Upbit", playbook: "лонг 1×, вхід через 60 хв, тримати до 8 год" })
    expect(triggerParts("binance_monitoring_tag").event).toBe("Тег моніторингу")
  })
})

describe("tape wording", () => {
  it("prints a rebalance with its P&L as a figure, not in the headline", () => {
    const line = describeEvent({ at: "2026-10-25T00:15:29+00:00", bot: "quant", kind: "rebalance", longs: 30, shorts: 30, pnl: -1.29, cost: 0.36, equity: 996.81, opening: false })
    expect(line.title).toBe("Ребаланс: 30 лонгів, 30 шортів")
    expect(line.amount).toBe(-1.29)
    expect(line.detail).toBe("витрати $0,36 · капітал $996,81")
  })

  it("names notice events in Ukrainian and marks notices without a tradable event as quiet", () => {
    const listing = describeEvent({ at: "2026-10-24T02:35:00+00:00", bot: "notice", kind: "notice", title: "버블맵스(BMT) KRW 마켓 디지털 자산 추가", source: "upbit", events: [{ type: "upbit_krw_listing", symbols: ["BMTUSDT"] }] })
    expect(listing.detail).toBe("Лістинг Upbit (KRW): BMT")
    expect(listing.quiet).toBe(false)
    const plain = describeEvent({ at: "2026-10-25T07:05:15+00:00", bot: "notice", kind: "notice", title: "Binance Futures Will Launch …", source: "binance", events: [] })
    expect(plain.detail).toBe("Binance · без торгової події")
    expect(plain.quiet).toBe(true)
  })

  it("flags a failed lab job", () => {
    const line = describeEvent({ at: "2026-10-25T16:57:01+00:00", bot: "lab", kind: "job", title: "Квант: період", status: "failed", job: "x" })
    expect(line.alert).toBe(true)
    expect(line.detail).toBe("тест завершився помилкою")
  })
})
