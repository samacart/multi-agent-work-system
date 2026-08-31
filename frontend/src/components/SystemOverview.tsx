import { api } from '../lib/api'
import Attention from './Attention'
import { usePolled } from '../lib/usePolled'

export default function SystemOverview() {
  const { data, error, loading } = usePolled(api.systemSummary, 5000)

  if (loading && !data) return <p className="muted">Loading…</p>
  if (error && !data) return <p className="error">Cannot reach the API: {error}</p>
  if (!data) return null

  return (
    <section>
      {/* Triage first: the counters are context, not the question. */}
      <Attention />

      <h2>System</h2>
      <dl className="kv">
        <dt>Phase</dt>
        <dd>
          {data.phase} — {data.phase_name}
        </dd>
        <dt>Environment</dt>
        <dd>{data.env}</dd>
        <dt>Agent runtime</dt>
        <dd>
          <code>{data.agent_runtime}</code>
          {data.agent_runtime === 'mock' ? (
            <span className="muted"> — deterministic scaffolding, no live model calls</span>
          ) : null}
          <span className="muted"> · available: {data.available_runtimes.join(', ')}</span>
        </dd>
        <dt>Embeddings</dt>
        <dd>
          <code>{data.embedding_provider}</code>
          {data.embedding_provider === 'hash' ? (
            <span className="muted"> — lexical, offline; set EMBEDDING_PROVIDER=openai for semantic</span>
          ) : null}
        </dd>
        <dt>Memory extraction</dt>
        <dd>
          <code>{data.memory_extractor}</code>
        </dd>
        <dt>GitHub</dt>
        <dd>
          {data.github_enabled ? (
            'configured'
          ) : (
            <span className="muted">off — set GITHUB_TOKEN to enable repo/issue/PR ingestion</span>
          )}
        </dd>
      </dl>

      <h2>Record counts</h2>
      <div className="counts">
        {Object.entries(data.counts).map(([label, count]) => (
          <div className="count" key={label}>
            <span className="count-value">{count}</span>
            <span className="count-label">{label.replace(/_/g, ' ')}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
