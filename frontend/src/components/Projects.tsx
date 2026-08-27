import { useCallback, useEffect, useState } from 'react'
import { api, type Artifact, type PlanningResult, type ProjectDetail, type Topic } from '../lib/api'
import ProjectPicker from './ProjectPicker'
import { useProjects } from '../lib/useProjects'

export default function Projects() {
  const { projects, selected, setSelected, error: listError, reload } = useProjects()
  const [topics, setTopics] = useState<Topic[]>([])
  const [name, setName] = useState('')
  const [goal, setGoal] = useState('')
  const [topicId, setTopicId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void api
      .topics()
      .then(setTopics)
      .catch(() => setTopics([]))
  }, [])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    try {
      const project = await api.createProject(name.trim(), goal.trim() || undefined, topicId || undefined)
      setName('')
      setGoal('')
      setError(null)
      await reload()
      setSelected(project.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Projects</h2>
      {listError ? <p className="error">{listError}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <form className="row-form" onSubmit={create}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="project name"
          aria-label="project name"
        />
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="goal — what does done look like?"
          aria-label="project goal"
        />
        <select value={topicId} onChange={(e) => setTopicId(e.target.value)} aria-label="topic">
          <option value="">no topic</option>
          {topics.map((topic) => (
            <option key={topic.id} value={topic.id}>
              {topic.name}
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy || !name.trim()}>
          {busy ? 'creating…' : 'create project'}
        </button>
      </form>

      <ProjectPicker projects={projects} selected={selected} onSelect={setSelected} />
      {selected ? <ProjectDetailView projectId={selected} onChanged={reload} /> : null}
    </section>
  )
}

function ProjectDetailView({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [openArtifact, setOpenArtifact] = useState<string | null>(null)
  const [planning, setPlanning] = useState(false)
  const [result, setResult] = useState<PlanningResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [d, a] = await Promise.all([api.project(projectId), api.artifacts(projectId)])
      setDetail(d)
      setArtifacts(a)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [projectId])

  useEffect(() => {
    setResult(null)
    setOpenArtifact(null)
    void load()
  }, [load])

  const plan = async () => {
    setPlanning(true)
    try {
      const planned = await api.planProject(projectId)
      setResult(planned)
      setError(planned.error)
      await load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPlanning(false)
    }
  }

  if (!detail) return <p className="muted">Loading project…</p>

  return (
    <div className="detail">
      {error ? <p className="error">{error}</p> : null}

      <h3>
        {detail.name} <span className={`badge badge-${detail.status}`}>{detail.status}</span>
      </h3>
      <p className="muted">{detail.goal}</p>

      <div className="counts">
        <div className="count">
          <span className="count-value">{Object.values(detail.task_counts).reduce((a, b) => a + b, 0)}</span>
          <span className="count-label">tasks</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.run_count}</span>
          <span className="count-label">agent runs</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.artifact_count}</span>
          <span className="count-label">artifacts</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.open_questions}</span>
          <span className="count-label">open questions</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.pending_approvals}</span>
          <span className="count-label">pending approvals</span>
        </div>
      </div>

      <div className="row-form">
        <button type="submit" onClick={() => void plan()} disabled={planning}>
          {planning ? 'planning…' : detail.run_count > 0 ? 're-plan' : 'run planning'}
        </button>
        <span className="muted">
          {detail.topic_name ? `Plans against topic memory: ${detail.topic_name}` : 'No topic linked — planning will have no memory to draw on'}
        </span>
      </div>

      {result ? (
        <p className="muted">
          {result.status} — {result.memories_used} memories, {result.runs.length} runs,{' '}
          {result.tasks_created} tasks created, {result.tasks_updated} updated, {result.questions_created} questions,{' '}
          {result.approvals_created} approvals
        </p>
      ) : null}

      <h2>Artifacts</h2>
      {artifacts.length === 0 ? (
        <p className="muted">No artifacts yet. Run planning to produce the brief, plan, and task breakdown.</p>
      ) : (
        <div>
          <div className="pill-row">
            {artifacts.map((artifact) => (
              <button
                key={artifact.id}
                className={artifact.id === openArtifact ? 'pill pill-active' : 'pill'}
                onClick={() => setOpenArtifact(artifact.id === openArtifact ? null : artifact.id)}
              >
                {artifact.type}
              </button>
            ))}
          </div>
          {openArtifact ? (
            <pre className="artifact">{artifacts.find((a) => a.id === openArtifact)?.content}</pre>
          ) : null}
        </div>
      )}

      {detail.brief ? (
        <>
          <h2>Brief</h2>
          <pre className="artifact">{detail.brief}</pre>
        </>
      ) : null}
    </div>
  )
}
