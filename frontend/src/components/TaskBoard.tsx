import { useCallback, useEffect, useState } from 'react'
import { api, TASK_STATUSES, type Blockers, type Task, type TaskStatus } from '../lib/api'
import Criteria from './Criteria'
import ProjectPicker from './ProjectPicker'
import { useProjects } from '../lib/useProjects'

export default function TaskBoard() {
  const { projects, selected, setSelected, error: listError } = useProjects()
  const [tasks, setTasks] = useState<Task[]>([])
  const [transitions, setTransitions] = useState<Record<string, string[]>>({})
  const [blockers, setBlockers] = useState<Record<string, Blockers>>({})
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!selected) return
    try {
      setTasks(await api.tasks(selected))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [selected])

  useEffect(() => {
    void load()
  }, [load])

  // Served rather than duplicated: a copy in the client would drift from the
  // state machine and the operator would learn the rules from a 409.
  useEffect(() => {
    void api
      .transitions()
      .then(setTransitions)
      .catch(() => setTransitions({}))
  }, [])

  // Blocked means nothing unless it names a cause.
  useEffect(() => {
    const blocked = tasks.filter((t) => t.status === 'blocked')
    if (blocked.length === 0) return
    void Promise.all(blocked.map((t) => api.blockers(t.id).catch(() => null))).then((results) => {
      const next: Record<string, Blockers> = {}
      results.forEach((b) => {
        if (b) next[b.task_id] = b
      })
      setBlockers(next)
    })
  }, [tasks])

  const move = async (task: Task, status: TaskStatus) => {
    try {
      await api.updateTask(task.id, { status })
      setError(null)
      await load()
    } catch (err) {
      // The API rejects illegal moves with 409 and says what is allowed.
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <section>
      <h2>Task board</h2>
      {listError ? <p className="error">{listError}</p> : null}
      <ProjectPicker projects={projects} selected={selected} onSelect={setSelected} />
      {error ? <p className="error">{error}</p> : null}

      {!selected ? null : tasks.length === 0 ? (
        <p className="muted">No tasks. Run planning on this project.</p>
      ) : (
        <div className="board">
          {TASK_STATUSES.map((status) => {
            const column = tasks.filter((t) => t.status === status)
            return (
              <div className={column.length ? 'column' : 'column column-empty'} key={status}>
                <div className="column-head">
                  {status.replace('_', ' ')} <span className="muted">{column.length}</span>
                </div>
                {column.map((task) => (
                  <div className="card" key={task.id}>
                    <div className="card-title">{task.title}</div>
                    <code>{task.agent_role}</code>
                    <Criteria task={task} onChanged={() => void load()} />
                    {task.metadata_json.dropped_from_plan ? (
                      <div className="dropped">
                        No longer in the plan — {task.metadata_json.dropped_from_plan}
                      </div>
                    ) : null}
                    {blockers[task.id] ? (
                      <div className="blocker">
                        {blockers[task.id].reason ? <div>{blockers[task.id].reason}</div> : null}
                        {blockers[task.id].approvals.map((a) => (
                          <div key={a.id}>
                            waiting on <a href="#queue">{a.action_type.replace(/_/g, ' ')}</a>
                          </div>
                        ))}
                        {blockers[task.id].dependencies.length > 0 ? (
                          <div>after: {blockers[task.id].dependencies.join(', ')}</div>
                        ) : null}
                      </div>
                    ) : null}

                    <select
                      value={task.status}
                      onChange={(e) => void move(task, e.target.value as TaskStatus)}
                      aria-label={`move ${task.title}`}
                    >
                      <option value={task.status}>{task.status.replace('_', ' ')}</option>
                      {(transitions[task.status] ?? []).map((s) => (
                        <option key={s} value={s}>
                          → {s.replace('_', ' ')}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
