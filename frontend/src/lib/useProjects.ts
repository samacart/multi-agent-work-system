import { useCallback, useEffect, useState } from 'react'
import { api, type Project } from './api'

/** Shared project list + selection, used by every project-scoped view. */
export function useProjects() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const rows = await api.projects()
      setProjects(rows)
      setSelected((current) => (current && rows.some((p) => p.id === current) ? current : rows[0]?.id ?? null))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { projects, selected, setSelected, error, reload: load }
}
