import type { Project } from '../lib/api'

export default function ProjectPicker({
  projects,
  selected,
  onSelect,
}: {
  projects: Project[] | null
  selected: string | null
  onSelect: (id: string) => void
}) {
  if (projects === null) return <p className="muted">Loading…</p>
  if (projects.length === 0)
    return <p className="muted">No projects yet. Create one in the Projects tab.</p>

  return (
    <div className="pill-row">
      {projects.map((project) => (
        <button
          key={project.id}
          className={project.id === selected ? 'pill pill-active' : 'pill'}
          onClick={() => onSelect(project.id)}
        >
          {project.name} <span className="muted">{project.status}</span>
        </button>
      ))}
    </div>
  )
}
