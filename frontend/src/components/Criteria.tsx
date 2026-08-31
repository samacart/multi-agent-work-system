import { useState } from 'react'
import { api, type EvidenceEntry, type Task } from '../lib/api'

const MARK: Record<string, string> = { met: '✓', not_met: '✗', unverified: '·' }

/**
 * Acceptance criteria with their verdicts — the thing that actually controls
 * promotion, and which the board previously rendered as a flat list of text.
 *
 * Human evidence is offered but never disguised: it is attributed, and shown
 * differently from evidence a run produced.
 */
export default function Criteria({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const [editing, setEditing] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const byCriterion = new Map(task.evidence.map((e) => [e.criterion, e]))

  const save = async (criterion: string) => {
    if (!text.trim()) {
      setError('Evidence is required to mark a criterion met')
      return
    }
    const entry: EvidenceEntry = {
      criterion,
      verdict: 'met',
      evidence: text.trim(),
      attributed_to: 'human',
    }
    try {
      await api.attachEvidence(task.id, entry)
      setEditing(null)
      setText('')
      setError(null)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <ul className="criteria">
      {task.acceptance_criteria.map((criterion) => {
        const found = byCriterion.get(criterion)
        const verdict = found?.verdict ?? 'unverified'
        const human = found?.attributed_to === 'human'
        return (
          <li key={criterion} className={`crit crit-${verdict}`}>
            <span className="crit-mark">{MARK[verdict] ?? '·'}</span>
            <span>{criterion}</span>
            {found?.evidence ? (
              <div className={human ? 'crit-evidence crit-human' : 'crit-evidence'}>
                {human ? 'you: ' : ''}
                {found.evidence}
              </div>
            ) : null}
            {verdict !== 'met' ? (
              editing === criterion ? (
                <div className="row-form">
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="what you checked, and how"
                    aria-label={`evidence for ${criterion}`}
                  />
                  <button type="submit" onClick={() => void save(criterion)}>
                    mark met
                  </button>
                  <button type="button" className="link" onClick={() => setEditing(null)}>
                    cancel
                  </button>
                </div>
              ) : (
                <button className="link" onClick={() => setEditing(criterion)}>
                  verify by hand
                </button>
              )
            ) : null}
          </li>
        )
      })}
      {error ? <li className="error">{error}</li> : null}
    </ul>
  )
}
