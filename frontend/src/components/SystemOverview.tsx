import { api } from '../lib/api'
import { usePolled } from '../lib/usePolled'

export default function SystemOverview() {
  const { data, error, loading } = usePolled(api.systemSummary, 5000)

  if (loading && !data) return <p className="muted">Loading…</p>
  if (error && !data) return <p className="error">Cannot reach the API: {error}</p>
  if (!data) return null

  return (
    <section>
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
          {data.agent_runtime}
          {data.agent_runtime === 'mock' ? <span className="muted"> (no live model calls)</span> : null}
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
