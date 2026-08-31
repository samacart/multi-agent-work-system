import { api, type AttentionItem } from '../lib/api'
import { usePolled } from '../lib/usePolled'

const KIND_LABEL: Record<string, string> = {
  degraded_dependency: 'system',
  approval: 'approval',
  failed_run: 'failed run',
  stale_run: 'stale run',
  blocked_task: 'blocked',
  open_question: 'question',
  config_warning: 'setup',
}

function age(seconds: number): string {
  if (seconds < 90) return 'just now'
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h`
  return `${Math.round(seconds / 86400)}d`
}

/** What each item costs if it is left alone — the thing the counters never said. */
function consequence(item: AttentionItem): string | null {
  if (item.kind === 'degraded_dependency') return 'nothing can run until this is fixed'
  if (item.kind === 'approval' && item.blast_radius > 0) {
    return `holding ${item.blast_radius} task${item.blast_radius === 1 ? '' : 's'}`
  }
  if (item.kind === 'stale_run') return 'probably a dead process, not work in progress'
  return null
}

export default function Attention() {
  const { data, error, loading } = usePolled(api.attention, 8000)

  if (loading && !data) return <p className="muted">Loading…</p>
  if (error && !data) return <p className="error">Cannot reach the API: {error}</p>
  if (!data) return null

  if (!data.needs_you) {
    // A deliberate state, not an absence. A quiet dashboard should read as
    // trustworthy rather than broken.
    return (
      <section>
        <h2>Attention</h2>
        <div className="quiet">
          <strong>Nothing needs you.</strong>
          <p className="muted">
            No approvals pending, no open questions, no failed or stalled runs, and every
            dependency is healthy.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section>
      <h2>
        Needs you ({data.count})
      </h2>
      <table className="grid">
        <thead>
          <tr>
            <th />
            <th>What</th>
            <th>Why</th>
            <th>Project</th>
            <th>Age</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => {
            const cost = consequence(item)
            return (
              <tr key={`${item.kind}-${item.action_id ?? item.title}`}>
                <td>
                  <span
                    className={
                      item.kind === 'degraded_dependency' || item.risk === 'high'
                        ? 'badge badge-bad'
                        : item.kind === 'open_question' || item.kind === 'config_warning'
                          ? 'badge'
                          : 'badge badge-busy'
                    }
                    title={`score ${item.score} — ${Object.entries(item.components)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(', ')}`}
                  >
                    {KIND_LABEL[item.kind] ?? item.kind}
                  </span>
                </td>
                <td>
                  <a href={item.link}>{item.title}</a>
                  {cost ? <div className="consequence">{cost}</div> : null}
                </td>
                <td className="muted">{item.why}</td>
                <td className="muted">{item.project_name ?? '—'}</td>
                <td className="muted">{age(item.age_seconds)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
