import { useCallback, useEffect, useState } from 'react'
import { api, type Topic } from '../lib/api'
import TopicDetail from './TopicDetail'

export default function Topics() {
  const [topics, setTopics] = useState<Topic[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const rows = await api.topics()
      setTopics(rows)
      setSelected((current) => current ?? rows[0]?.id ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    try {
      const topic = await api.createTopic(name.trim(), description.trim() || undefined)
      setName('')
      setDescription('')
      setError(null)
      await load()
      setSelected(topic.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Topics</h2>
      {error ? <p className="error">{error}</p> : null}

      <form className="row-form" onSubmit={create}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="topic name, e.g. customer onboarding"
          aria-label="topic name"
        />
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="description (optional)"
          aria-label="topic description"
        />
        <button type="submit" disabled={busy || !name.trim()}>
          {busy ? 'creating…' : 'create topic'}
        </button>
      </form>

      {topics === null ? (
        <p className="muted">Loading…</p>
      ) : topics.length === 0 ? (
        <p className="muted">No topics yet. Create one above, then register a source to ingest.</p>
      ) : (
        <div className="pill-row">
          {topics.map((topic) => (
            <button
              key={topic.id}
              className={topic.id === selected ? 'pill pill-active' : 'pill'}
              onClick={() => setSelected(topic.id)}
            >
              {topic.name}
            </button>
          ))}
        </div>
      )}

      {selected ? <TopicDetail topicId={selected} /> : null}
    </section>
  )
}
