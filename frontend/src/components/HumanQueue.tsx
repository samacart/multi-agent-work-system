import { useCallback, useEffect, useState } from 'react'
import { api, type Approval, type Decision } from '../lib/api'
import ProjectPicker from './ProjectPicker'
import { useProjects } from '../lib/useProjects'

export default function HumanQueue() {
  const { projects, selected, setSelected, error: listError } = useProjects()
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!selected) return
    try {
      const [a, d] = await Promise.all([api.approvals(selected), api.decisions(selected)])
      setApprovals(a)
      setDecisions(d)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [selected])

  useEffect(() => {
    void load()
  }, [load])

  const respond = async (approval: Approval, status: 'approved' | 'rejected') => {
    try {
      await api.respondToApproval(approval.id, status)
      setError(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const answer = async (decision: Decision) => {
    const text = (answers[decision.id] ?? '').trim()
    if (!text) return
    try {
      await api.answerDecision(decision.id, text)
      setAnswers((current) => ({ ...current, [decision.id]: '' }))
      setError(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const pending = approvals.filter((a) => a.status === 'pending')
  const resolved = approvals.filter((a) => a.status !== 'pending')
  const open = decisions.filter((d) => !d.answer)
  const answered = decisions.filter((d) => d.answer)

  return (
    <section>
      <h2>Human queue</h2>
      {listError ? <p className="error">{listError}</p> : null}
      <ProjectPicker projects={projects} selected={selected} onSelect={setSelected} />
      {error ? <p className="error">{error}</p> : null}

      {!selected ? null : (
        <>
          <h2>Approvals needed ({pending.length})</h2>
          {pending.length === 0 ? (
            <p className="muted">Nothing waiting on you.</p>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Risk</th>
                  <th>Summary</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {pending.map((approval) => (
                  <tr key={approval.id}>
                    <td>
                      <code>{approval.action_type}</code>
                    </td>
                    <td>
                      <span className={approval.risk_level === 'high' ? 'badge badge-bad' : 'badge'}>
                        {approval.risk_level}
                      </span>
                    </td>
                    <td>{approval.action_summary}</td>
                    <td className="actions">
                      <button className="link" onClick={() => void respond(approval, 'approved')}>
                        approve
                      </button>
                      <button className="link link-bad" onClick={() => void respond(approval, 'rejected')}>
                        reject
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Open questions ({open.length})</h2>
          {open.length === 0 ? (
            <p className="muted">No open questions.</p>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Why it matters</th>
                  <th>Answer</th>
                </tr>
              </thead>
              <tbody>
                {open.map((decision) => (
                  <tr key={decision.id}>
                    <td>{decision.question}</td>
                    <td className="muted">{decision.rationale}</td>
                    <td>
                      <div className="row-form">
                        <input
                          value={answers[decision.id] ?? ''}
                          onChange={(e) =>
                            setAnswers((current) => ({ ...current, [decision.id]: e.target.value }))
                          }
                          placeholder="your decision"
                          aria-label={`answer: ${decision.question}`}
                        />
                        <button type="submit" onClick={() => void answer(decision)}>
                          record
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {resolved.length + answered.length > 0 ? (
            <>
              <h2>Resolved</h2>
              <table className="grid">
                <tbody>
                  {resolved.map((approval) => (
                    <tr key={approval.id}>
                      <td>
                        <code>{approval.action_type}</code>
                      </td>
                      <td>
                        <span className={approval.status === 'approved' ? 'badge badge-ok' : 'badge badge-bad'}>
                          {approval.status}
                        </span>
                      </td>
                      <td className="muted">{approval.action_summary}</td>
                    </tr>
                  ))}
                  {answered.map((decision) => (
                    <tr key={decision.id}>
                      <td colSpan={2}>{decision.question}</td>
                      <td>
                        {decision.answer} <span className="muted">— {decision.decided_by}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
        </>
      )}
    </section>
  )
}
