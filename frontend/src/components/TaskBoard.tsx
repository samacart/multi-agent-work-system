import { useCallback, useEffect, useState } from 'react'
import { api, TASK_STATUSES, type Task, type TaskStatus } from '../lib/api'
import ProjectPicker from './ProjectPicker'
import { useProjects } from '../lib/useProjects'

export default function TaskBoard() {
  const { projects, selected, setSelected, error: listError } = useProjects()
  const [tasks, setTasks] = useState<Task[]>([])
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
              <div className="column" key={status}>
                <div className="column-head">
                  {status.replace('_', ' ')} <span className="muted">{column.length}</span>
                </div>
                {column.map((task) => (
                  <div className="card" key={task.id}>
                    <div className="card-title">{task.title}</div>
                    <code>{task.agent_role}</code>
                    <ul className="criteria">
                      {task.acceptance_criteria.map((criterion) => (
                        <li key={criterion}>{criterion}</li>
                      ))}
                    </ul>
                    {task.metadata_json.depends_on?.length ? (
                      <div className="muted">after: {task.metadata_json.depends_on.join(', ')}</div>
                    ) : null}
                    <select
                      value={task.status}
                      onChange={(e) => void move(task, e.target.value as TaskStatus)}
                      aria-label={`move ${task.title}`}
                    >
                      {TASK_STATUSES.map((s) => (
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
