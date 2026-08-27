export default function Placeholder({ title, phase, items }: { title: string; phase: string; items: string[] }) {
  return (
    <section>
      <h2>{title}</h2>
      <p className="muted">
        Not built yet — arrives in <strong>{phase}</strong>. The tables and API surface for this view already exist.
      </p>
      <ul className="checklist">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  )
}
