import { api, type Readiness } from '../lib/api'
import { usePolled } from '../lib/usePolled'

function Dot({ ok }: { ok: boolean }) {
  return <span className={ok ? 'dot dot-ok' : 'dot dot-bad'} aria-hidden />
}

export default function StatusBar() {
  const health = usePolled(api.health, 10000)
  const ready = usePolled<Readiness>(api.readiness, 5000)

  const apiOk = health.data?.status === 'ok'
  const checks = ready.data?.checks ?? {}

  return (
    <div className="statusbar">
      <span className="statusbar-item">
        <Dot ok={apiOk} /> api {health.error ? <em>unreachable</em> : health.data?.version ?? '…'}
      </span>
      {Object.entries(checks).map(([name, check]) => (
        <span className="statusbar-item" key={name}>
          <Dot ok={check.status === 'ok'} /> {name}
          {check.detail ? <em> {check.detail}</em> : null}
          {typeof check.queue_depth === 'number' ? <em> queue {check.queue_depth}</em> : null}
        </span>
      ))}
      <span className="statusbar-spacer" />
      <span className="statusbar-item muted">{api.baseUrl}</span>
    </div>
  )
}
