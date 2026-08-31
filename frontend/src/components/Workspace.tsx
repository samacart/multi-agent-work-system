import { useCallback, useEffect, useState } from 'react'
import { api, type WorkspaceStatus } from '../lib/api'

/**
 * Where a project's agents actually run.
 *
 * This is not a cosmetic field: the path becomes an agent's working directory
 * with shell access, so the validation state is shown rather than assumed, and
 * a warning is shown even when the workspace is usable.
 */
export default function Workspace({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<WorkspaceStatus | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const next = await api.workspace(projectId)
      setStatus(next)
      setDraft(next.project_workspace ?? '')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [projectId])

  useEffect(() => {
    setEditing(false)
    void load()
  }, [load])

  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await api.setWorkspace(projectId, draft.trim())
      setError(null)
      setEditing(false)
      await load()
    } catch (err) {
      // The API rejects an unusable path with the validation reason.
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (!status) return null
  const { validation } = status

  return (
    <div className="workspace">
      <h2>Workspace</h2>
      {error ? <p className="error">{error}</p> : null}

      {editing ? (
        <form className="row-form" onSubmit={save}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="/path/to/repo — must be inside ALLOWED_WORKSPACE_ROOTS"
            aria-label="workspace path"
          />
          <button type="submit" disabled={busy}>
            {busy ? 'checking…' : 'save'}
          </button>
          <button type="button" className="link" onClick={() => setEditing(false)}>
            cancel
          </button>
          <span className="muted">Leave empty to fall back to the global setting.</span>
        </form>
      ) : (
        <div className="row-form">
          <span className={validation.valid ? 'badge badge-ok' : 'badge badge-bad'}>
            {validation.valid ? 'usable' : 'unusable'}
          </span>
          <code>{status.resolved_workspace ?? 'none configured'}</code>
          {status.using_global_fallback ? (
            <span className="muted">global fallback — this project has not set one</span>
          ) : null}
          <button className="link" onClick={() => setEditing(true)}>
            {status.project_workspace ? 'change' : 'set for this project'}
          </button>
        </div>
      )}

      {validation.valid ? (
        <p className="muted">
          Branch <code>{validation.branch}</code>
          {validation.dirty_files > 0 ? ` · ${validation.dirty_files} uncommitted` : ' · clean'}
        </p>
      ) : validation.reason ? (
        <p className="error">{validation.reason}</p>
      ) : null}

      {validation.warnings.length > 0 ? (
        <ul className="checklist">
          {validation.warnings.map((w) => (
            <li key={w} className="warn">
              {w}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
