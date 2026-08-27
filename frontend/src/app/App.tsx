import { useEffect, useState } from 'react'
import StatusBar from '../components/StatusBar'
import SystemOverview from '../components/SystemOverview'
import AgentProfiles from '../components/AgentProfiles'
import Topics from '../components/Topics'
import Projects from '../components/Projects'
import TaskBoard from '../components/TaskBoard'
import AgentRuns from '../components/AgentRuns'
import HumanQueue from '../components/HumanQueue'

type View = { id: string; label: string; render: () => JSX.Element }

const VIEWS: View[] = [
  { id: 'overview', label: 'Overview', render: () => <SystemOverview /> },
  { id: 'agents', label: 'Agents', render: () => <AgentProfiles /> },
  { id: 'topics', label: 'Topics', render: () => <Topics /> },
  { id: 'projects', label: 'Projects', render: () => <Projects /> },
  { id: 'board', label: 'Task board', render: () => <TaskBoard /> },
  { id: 'runs', label: 'Agent runs', render: () => <AgentRuns /> },
  { id: 'queue', label: 'Human queue', render: () => <HumanQueue /> },
]

function viewFromHash(): string {
  const id = window.location.hash.replace(/^#/, '')
  return VIEWS.some((v) => v.id === id) ? id : VIEWS[0].id
}

export default function App() {
  // The tab lives in the URL hash so a view can be linked to and reloaded into.
  const [active, setActive] = useState(viewFromHash)

  useEffect(() => {
    const onHashChange = () => setActive(viewFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const select = (id: string) => {
    window.location.hash = id
    setActive(id)
  }

  const view = VIEWS.find((v) => v.id === active) ?? VIEWS[0]

  return (
    <div className="shell">
      <header className="header">
        <h1>Mission Control</h1>
        <span className="subtitle">Multi-Agent Work System</span>
      </header>

      <StatusBar />

      <nav className="tabs">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            className={v.id === active ? 'tab tab-active' : 'tab'}
            onClick={() => select(v.id)}
          >
            {v.label}
          </button>
        ))}
      </nav>

      <main className="content">{view.render()}</main>
    </div>
  )
}
