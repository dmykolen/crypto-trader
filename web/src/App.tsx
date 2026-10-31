import { AnimatePresence, MotionConfig, motion } from "motion/react"
import { useState } from "react"
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom"

import { CommandMenu } from "./components/CommandMenu"
import { useAlerts } from "./lib/alerts"
import { Rail, TopBar } from "./components/Shell"
import { Evidence } from "./pages/Evidence"
import { JobPage } from "./pages/JobPage"
import { Lab } from "./pages/Lab"
import { NoticeBot } from "./pages/NoticeBot"
import { Overview, Page } from "./pages/Overview"
import { Processes } from "./pages/Processes"
import { QuantBot } from "./pages/QuantBot"

function NotFound() {
  return (
    <Page>
      <h1 className="display pt-8 text-[24px] font-semibold">Такої сторінки немає</h1>
      <p className="mt-2 text-text-2">
        Поверніться на <Link to="/">огляд</Link>.
      </p>
    </Page>
  )
}

function Alerts() {
  useAlerts()
  return null
}

export function App() {
  const location = useLocation()
  const [command, setCommand] = useState(false)
  return (
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen">
        <TopBar onCommand={() => setCommand(true)} />
        <div className="md:flex">
          <Rail />
          <main className="min-w-0 flex-1">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, transition: { duration: 0.12 } }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              >
                <Routes location={location}>
                  <Route path="/" element={<Overview />} />
                  <Route path="/bots/notice" element={<NoticeBot />} />
                  <Route path="/bots/quant" element={<QuantBot />} />
                  <Route path="/lab" element={<Lab />} />
                  <Route path="/lab/:id" element={<JobPage />} />
                  <Route path="/evidence" element={<Evidence />} />
                  <Route path="/processes" element={<Processes />} />
                  <Route path="/system" element={<Navigate to="/processes" replace />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
        <CommandMenu open={command} setOpen={setCommand} />
        <Alerts />
      </div>
    </MotionConfig>
  )
}
