import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  MEMORY_TYPES,
  type Memory,
  type MemorySearchHit,
  type Source,
  type TopicDetail as TopicDetailType,
} from '../lib/api'

const LOCAL_SOURCE_TYPES = ['pasted_text', 'local_file', 'local_folder']
const GITHUB_SOURCE_TYPES = ['github_repo', 'github_issue', 'github_pr']

function statusClass(status: string) {
  if (status === 'ingested') return 'badge badge-ok'
  if (status === 'failed') return 'badge badge-bad'
  if (status === 'ingesting') return 'badge badge-busy'
  return 'badge'
}

export default function TopicDetail({ topicId }: { topicId: string }) {
  const [detail, setDetail] = useState<TopicDetailType | null>(null)
  const [sources, setSources] = useState<Source[]>([])
  const [memories, setMemories] = useState<Memory[]>([])
  const [typeFilter, setTypeFilter] = useState('')
  const [error, setError] = useState<string | null>(null)

  const [sourceType, setSourceType] = useState<string>('pasted_text')
  const [sourceName, setSourceName] = useState('')
  const [sourceUri, setSourceUri] = useState('')
  const [sourceText, setSourceText] = useState('')
  const [busy, setBusy] = useState(false)

  const [githubEnabled, setGithubEnabled] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<MemorySearchHit[] | null>(null)
  const [searching, setSearching] = useState(false)

  const load = useCallback(async () => {
    try {
      const [d, s, m] = await Promise.all([
        api.topic(topicId),
        api.sources(topicId),
        api.memories(topicId, typeFilter || undefined),
      ])
      setDetail(d)
      setSources(s)
      setMemories(m)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [topicId, typeFilter])

  useEffect(() => {
    setHits(null)
    void load()
  }, [load])

  useEffect(() => {
    void api
      .githubStatus()
      .then((status) => setGithubEnabled(status.enabled))
      .catch(() => setGithubEnabled(false))
  }, [])

  const sourceTypes = githubEnabled ? [...LOCAL_SOURCE_TYPES, ...GITHUB_SOURCE_TYPES] : LOCAL_SOURCE_TYPES
  const isGithub = sourceType.startsWith('github_')

  // While anything is mid-ingestion, poll so the status flips without a manual refresh.
  const ingesting = sources.some((s) => s.status === 'ingesting')
  const loadRef = useRef(load)
  loadRef.current = load
  useEffect(() => {
    if (!ingesting) return
    const id = setInterval(() => void loadRef.current(), 2000)
    return () => clearInterval(id)
  }, [ingesting])

  const addSource = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await api.createSource(topicId, {
        type: sourceType,
        name: sourceName.trim() || (sourceType === 'pasted_text' ? 'pasted text' : sourceUri),
        uri: sourceType === 'pasted_text' ? undefined : sourceUri.trim(),
        text: sourceType === 'pasted_text' ? sourceText : undefined,
      })
      setSourceName('')
      setSourceUri('')
      setSourceText('')
      setError(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const ingest = async (source: Source) => {
    try {
      const result = await api.ingestSource(source.id, 'async')
      if (result.summary?.error) setError(result.summary.error)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const search = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const response = await api.searchMemory(query.trim(), topicId, typeFilter ? [typeFilter] : undefined)
      setHits(response.results)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSearching(false)
    }
  }

  if (!detail) return <p className="muted">Loading topic…</p>

  return (
    <div className="detail">
      {error ? <p className="error">{error}</p> : null}

      <h3>
        {detail.name} <span className="muted">{detail.description}</span>
      </h3>
      <div className="counts">
        <div className="count">
          <span className="count-value">{detail.source_count}</span>
          <span className="count-label">sources</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.chunk_count}</span>
          <span className="count-label">chunks</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.memory_count}</span>
          <span className="count-label">memories</span>
        </div>
        <div className="count">
          <span className="count-value">{detail.project_count}</span>
          <span className="count-label">projects</span>
        </div>
      </div>

      <h2>Sources</h2>
      {!githubEnabled ? (
        <p className="muted">
          GitHub sources are hidden because the integration is not configured. Set <code>GITHUB_TOKEN</code> to
          enable repo, issue, and pull request ingestion.
        </p>
      ) : null}
      <form className="row-form" onSubmit={addSource}>
        <select value={sourceType} onChange={(e) => setSourceType(e.target.value)} aria-label="source type">
          {sourceTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          value={sourceName}
          onChange={(e) => setSourceName(e.target.value)}
          placeholder="source name"
          aria-label="source name"
        />
        {sourceType === 'pasted_text' ? (
          <textarea
            value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            placeholder="paste notes, a spec, a thread…"
            aria-label="pasted text"
            rows={3}
          />
        ) : (
          <input
            value={sourceUri}
            onChange={(e) => setSourceUri(e.target.value)}
            placeholder={
              isGithub
                ? 'https://github.com/owner/repo — or an issue / pull URL'
                : '/data/sources/… (must be inside an allowed root)'
            }
            aria-label="source path"
          />
        )}
        <button type="submit" disabled={busy}>
          {busy ? 'adding…' : 'register source'}
        </button>
      </form>

      {sources.length === 0 ? (
        <p className="muted">No sources registered.</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Status</th>
              <th>Last ingestion</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => {
              const last = source.metadata_json.last_ingestion
              return (
                <tr key={source.id}>
                  <td>
                    {source.name}
                    {source.uri ? <div className="muted">{source.uri}</div> : null}
                  </td>
                  <td>
                    <code>{source.type}</code>
                  </td>
                  <td>
                    <span className={statusClass(source.status)}>{source.status}</span>
                  </td>
                  <td className="muted">
                    {last ? (
                      last.error ? (
                        <span className="error">{last.error}</span>
                      ) : (
                        `${last.chunks_created} chunks, ${last.memories_created} memories` +
                        (last.chunks_skipped_duplicate + last.memories_skipped_duplicate > 0
                          ? ` (${last.chunks_skipped_duplicate + last.memories_skipped_duplicate} duplicates skipped)`
                          : '')
                      )
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <button className="link" onClick={() => void ingest(source)} disabled={source.status === 'ingesting'}>
                      {source.status === 'ingesting' ? 'ingesting…' : 'ingest'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <h2>Memory</h2>
      <form className="row-form" onSubmit={search}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search this topic's memory…"
          aria-label="memory search"
        />
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="memory type filter">
          <option value="">all types</option>
          {MEMORY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t} {detail.memory_types[t] ? `(${detail.memory_types[t]})` : ''}
            </option>
          ))}
        </select>
        <button type="submit" disabled={searching || !query.trim()}>
          {searching ? 'searching…' : 'search'}
        </button>
        {hits ? (
          <button type="button" className="link" onClick={() => setHits(null)}>
            clear
          </button>
        ) : null}
      </form>

      {hits ? (
        hits.length === 0 ? (
          <p className="muted">No matches.</p>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Score</th>
                <th>Type</th>
                <th>Memory</th>
              </tr>
            </thead>
            <tbody>
              {hits.map((hit) => (
                <tr key={hit.memory.id}>
                  <td title={JSON.stringify(hit.components, null, 2)}>{hit.score.toFixed(3)}</td>
                  <td>
                    <code>{hit.memory.type}</code>
                  </td>
                  <td>{hit.memory.content}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : memories.length === 0 ? (
        <p className="muted">No memories yet. Register a source and run ingestion.</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>Type</th>
              <th>Imp.</th>
              <th>Conf.</th>
              <th>Memory</th>
            </tr>
          </thead>
          <tbody>
            {memories.map((memory) => (
              <tr key={memory.id}>
                <td>
                  <code>{memory.type}</code>
                </td>
                <td className="muted">{memory.importance.toFixed(2)}</td>
                <td className="muted">{memory.confidence.toFixed(2)}</td>
                <td>{memory.content}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
