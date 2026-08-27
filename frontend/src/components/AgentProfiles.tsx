import { Fragment, useState } from 'react'
import { api } from '../lib/api'
import { usePolled } from '../lib/usePolled'

export default function AgentProfiles() {
  const { data, error, loading } = usePolled(api.agentProfiles, 30000)
  const [expanded, setExpanded] = useState<string | null>(null)

  if (loading && !data) return <p className="muted">Loading…</p>
  if (error && !data) return <p className="error">Cannot reach the API: {error}</p>
  if (!data?.length) return <p className="muted">No agent profiles seeded yet.</p>

  return (
    <section>
      <h2>Agent profiles ({data.length})</h2>
      <table className="grid">
        <thead>
          <tr>
            <th>Name</th>
            <th>Role</th>
            <th>Allowed tools</th>
            <th>Gated actions</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.map((profile) => (
            <Fragment key={profile.id}>
              <tr>
                <td>{profile.name}</td>
                <td>
                  <code>{profile.role}</code>
                </td>
                <td className="muted">{profile.allowed_tools_json.join(', ') || '—'}</td>
                <td className="muted">{profile.approval_rules_json.requires_approval?.length ?? 0}</td>
                <td>
                  <button
                    className="link"
                    onClick={() => setExpanded(expanded === profile.id ? null : profile.id)}
                  >
                    {expanded === profile.id ? 'hide prompt' : 'prompt'}
                  </button>
                </td>
              </tr>
              {expanded === profile.id ? (
                <tr>
                  <td colSpan={5}>
                    <pre className="prompt">{profile.system_prompt}</pre>
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
    </section>
  )
}
