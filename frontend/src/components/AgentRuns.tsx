import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, type AgentRun } from '../lib/api'
import ProjectPicker from './ProjectPicker'
import { useProjects } from '../lib/useProjects'

function duration(run: AgentRun): string {
  if (!run.started_at || !run.completed_at) return '—'
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  return `${ms} ms`
}

export default function AgentRuns() {
  const { projects, selected, setSelected, error: listError } = useProjects()
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!selected) return
    try {
      setRuns(await api.runs(selected))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [selected])

  useEffect(() => {
    setOpen(null)
    void load()
  }, [load])

  return (
    <section>
      <h2>Agent runs</h2>
      {listError ? <p className="error">{listError}</p> : null}
      <ProjectPicker projects={projects} selected={selected} onSelect={setSelected} />
      {error ? <p className="error">{error}</p> : null}

      {!selected ? null : runs.length === 0 ? (
        <p className="muted">No agent runs yet.</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Task</th>
              <th>Runtime</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Started</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <Fragment key={run.id}>
                <tr>
                  <td>
                    <code>{run.input.task ?? '—'}</code>
                    <div className="muted">{run.input.instruction}</div>
                  </td>
                  <td className="muted">{run.input.runtime}</td>
                  <td>
                    <span className={run.status === 'succeeded' ? 'badge badge-ok' : run.status === 'failed' ? 'badge badge-bad' : 'badge'}>
                      {run.status}
                    </span>
                  </td>
                  <td className="muted">{duration(run)}</td>
                  <td className="muted">{run.started_at ? new Date(run.started_at).toLocaleTimeString() : '—'}</td>
                  <td>
                    <button className="link" onClick={() => setOpen(open === run.id ? null : run.id)}>
                      {open === run.id ? 'hide' : 'output'}
                    </button>
                  </td>
                </tr>
                {open === run.id ? (
                  <tr>
                    <td colSpan={6}>
                      {run.error ? <p className="error">{run.error}</p> : null}
                      <pre className="artifact">{JSON.stringify(run.output, null, 2)}</pre>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
