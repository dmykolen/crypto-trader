import { Link, Route, Routes } from "react-router-dom"

import { Masthead } from "./components/Masthead"
import { Evidence } from "./pages/Evidence"
import { JobPage } from "./pages/JobPage"
import { Lab } from "./pages/Lab"
import { NoticeBot } from "./pages/NoticeBot"
import { Overview, Page } from "./pages/Overview"
import { QuantBot } from "./pages/QuantBot"
import { System } from "./pages/System"

function NotFound() {
  return (
    <Page>
      <h1 className="head pt-8 text-[2rem] font-extrabold">Такої сторінки у випуску немає</h1>
      <p className="mt-2 text-ink-2">
        Поверніться на <Link to="/">огляд</Link>.
      </p>
    </Page>
  )
}

export function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Masthead />
      <div className="flex-1">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/bots/notice" element={<NoticeBot />} />
          <Route path="/bots/quant" element={<QuantBot />} />
          <Route path="/lab" element={<Lab />} />
          <Route path="/lab/:id" element={<JobPage />} />
          <Route path="/evidence" element={<Evidence />} />
          <Route path="/system" element={<System />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
      <footer className="mx-auto w-full max-w-[1480px] px-5 pb-6 md:px-8">
        <div className="rule-double pt-2 text-[11.5px] text-ink-3">Локальний пульт на цьому Mac · дані Binance та Upbit · реальні гроші лише після вашого підтвердження</div>
      </footer>
    </div>
  )
}
