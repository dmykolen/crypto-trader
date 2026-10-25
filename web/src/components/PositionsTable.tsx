import { fmt } from "../lib/format"
import type { QuantPosition } from "../lib/types"
import { Signed } from "./Print"

function Rows({ rows }: { rows: QuantPosition[] }) {
  return (
    <>
      {rows.map((p) => (
        <tr key={p.symbol}>
          <td className="font-semibold">{p.symbol.replace(/USDT$/, "")}</td>
          <td className="r num">{fmt.pctPlain(100 * Math.abs(p.weight), 2)}</td>
          <td className="r num">{fmt.usd(p.notional)}</td>
          <td className="r num">{fmt.price(p.entry)}</td>
          <td className="r num">{fmt.price(p.price, p.entry)}</td>
          <td className="r">
            <Signed value={p.move === null ? null : p.side === "long" ? p.move : -p.move} digits={4}>{p.move === null ? "—" : fmt.pct(100 * p.move, 2)}</Signed>
          </td>
          <td className="r">
            <Signed value={p.pnl} arrow={false}>
              {fmt.pnl(p.pnl)}
            </Signed>
          </td>
        </tr>
      ))}
    </>
  )
}

/** The book in agate: longs and shorts as two listings, marked to the latest exchange price. */
export function PositionsTable({ positions, limit }: { positions: QuantPosition[]; limit?: number }) {
  const longs = positions.filter((p) => p.side === "long")
  const shorts = positions.filter((p) => p.side === "short")
  const cut = (rows: QuantPosition[]) => (limit ? rows.slice(0, limit) : rows)
  return (
    <div className="overflow-x-auto">
      <table className="agate min-w-[560px]">
        <thead>
          <tr>
            <th>Токен</th>
            <th className="r">Вага</th>
            <th className="r">Сума</th>
            <th className="r">Вхід</th>
            <th className="r">Ціна</th>
            <th className="r">Рух</th>
            <th className="r">P&L</th>
          </tr>
        </thead>
        <tbody>
          <tr className="sub">
            <td colSpan={7}>
              Лонги · {longs.length}
              {limit && longs.length > limit ? `, показано ${limit}` : ""}
            </td>
          </tr>
          <Rows rows={cut(longs)} />
          <tr className="sub">
            <td colSpan={7}>
              Шорти · {shorts.length}
              {limit && shorts.length > limit ? `, показано ${limit}` : ""}
            </td>
          </tr>
          <Rows rows={cut(shorts)} />
        </tbody>
      </table>
    </div>
  )
}
