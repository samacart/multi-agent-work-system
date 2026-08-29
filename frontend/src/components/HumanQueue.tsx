import { Fragment, useCallback, useEffect, useState } from 'react'
import {
  api,
  APPROVAL_ARTIFACT,
  GATED_ROLES,
  type Approval,
  type ApprovalBriefing,
  type Artifact,
  type Decision,
  type Task,
} from '../lib/api'
import Markdown from './Markdown'
import ProjectPicker from './ProjectPicker'
import { useProjects } from '../lib/useProjects'

function Briefing({ briefing, reviewedBy }: { briefing: ApprovalBriefing; reviewedBy?: string }) {
  const tone =
    briefing.recommendation === 'approve'
      ? 'rec rec-approve'
      : briefing.recommendation === 'revise'
        ? 'rec rec-revise'
        : 'rec rec-changes'

  return (
    <div className="briefing">
      <div>
        <span className={tone}>{briefing.recommendation.replace(/_/g, ' ')}</span>
        {reviewedBy ? <span className="muted"> — reviewed by {reviewedBy.replace(/_/g, ' ')}</span> : null}
      </div>
      <p>{briefing.summary}</p>
      {briefing.rationale ? <p className="muted">{briefing.rationale}</p> : null}
      {briefing.contradicts_earlier_stage?.length ? (
        <div className="error">
          Contradicts an earlier approved stage:
          <ul className="checklist">
            {briefing.contradicts_earlier_stage.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {briefing.concerns?.length ? (
        <div>
          <strong>What would make this the wrong call</strong>
          <ul className="checklist">
            {briefing.concerns.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {briefing.key_points?.length ? (
        <div className="muted">Covers: {briefing.key_points.join(' · ')}</div>
      ) : null}
    </div>
  )
}

export default function HumanQueue() {
  const { projects, selected, setSelected, error: listError } = useProjects()
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [openApproval, setOpenApproval] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!selected) return
    try {
      const [a, d, art, t] = await Promise.all([
        api.approvals(selected),
        api.decisions(selected),
        api.artifacts(selected).catch(() => []),
        api.tasks(selected).catch(() => []),
      ])
      setApprovals(a)
      setDecisions(d)
      setArtifacts(art)
      setTasks(t)
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

  /** The artifact this gate is actually asking about, if it is a stage gate. */
  const artifactFor = (approval: Approval) => {
    const type = APPROVAL_ARTIFACT[approval.action_type]
    return type ? artifacts.find((a) => a.type === type) : undefined
  }

  /** What stays blocked while this gate is pending. */
  const blockedBy = (approval: Approval) =>
    APPROVAL_ARTIFACT[approval.action_type]
      ? []
      : tasks.filter((t) => t.agent_role && GATED_ROLES.includes(t.agent_role) && t.status !== 'done')

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
                {pending.map((approval) => {
                  const artifact = artifactFor(approval)
                  const blocked = blockedBy(approval)
                  const isOpen = openApproval === approval.id
                  return (
                    <Fragment key={approval.id}>
                      <tr>
                        <td>
                          <code>{approval.action_type}</code>
                        </td>
                        <td>
                          <span className={approval.risk_level === 'high' ? 'badge badge-bad' : 'badge'}>
                            {approval.risk_level}
                          </span>
                        </td>
                        <td>
                          {approval.action_summary}
                          {approval.metadata_json?.briefing ? (
                            <Briefing
                              briefing={approval.metadata_json.briefing}
                              reviewedBy={approval.metadata_json.reviewed_by}
                            />
                          ) : approval.metadata_json?.briefing_error ? (
                            <div className="muted">No briefing available — read the artifact yourself.</div>
                          ) : null}
                          {artifact ? (
                            <div>
                              <button
                                className="link"
                                onClick={() => setOpenApproval(isOpen ? null : approval.id)}
                              >
                                {isOpen ? 'hide' : 'read'} the {artifact.type.replace('_', ' ')} →
                              </button>
                            </div>
                          ) : null}
                          {!artifact && APPROVAL_ARTIFACT[approval.action_type] ? (
                            <div className="muted">
                              This gate refers to a {APPROVAL_ARTIFACT[approval.action_type].replace('_', ' ')},
                              which has not been produced yet.
                            </div>
                          ) : null}
                          {blocked.length ? (
                            <div className="muted">
                              Blocks {blocked.length} task{blocked.length === 1 ? '' : 's'} while pending:{' '}
                              {blocked
                                .slice(0, 3)
                                .map((t) => t.title)
                                .join('; ')}
                              {blocked.length > 3 ? ` and ${blocked.length - 3} more` : ''}
                            </div>
                          ) : null}
                        </td>
                        <td className="actions">
                          <button className="link" onClick={() => void respond(approval, 'approved')}>
                            approve
                          </button>
                          <button className="link link-bad" onClick={() => void respond(approval, 'rejected')}>
                            reject
                          </button>
                        </td>
                      </tr>
                      {isOpen && artifact ? (
                        <tr>
                          <td colSpan={4}>
                            <Markdown>{artifact.content}</Markdown>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  )
                })}
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
                    <td>
                      {decision.question}
                      {decision.metadata_json?.options?.length ? (
                        <ul className="checklist">
                          {decision.metadata_json.options.map((o) => (
                            <li key={o}>
                              {o}
                              {o === decision.metadata_json?.recommendation ? (
                                <span className="rec-inline"> ← recommended</span>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </td>
                    <td className="muted">
                      {decision.rationale}
                      {decision.metadata_json?.recommendation &&
                      !decision.metadata_json?.options?.includes(decision.metadata_json.recommendation) ? (
                        <div className="rec-inline">Recommended: {decision.metadata_json.recommendation}</div>
                      ) : null}
                    </td>
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
