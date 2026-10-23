import { Link } from 'react-router-dom'
import { api } from '../api'
import { useLoad } from '../hooks'
import { Badge, Logo, Spinner } from '../ui'

const USES: [string, string, string][] = [
  ['Reading a document', 'Gemini reads an uploaded certificate and drafts the fields. It only runs when the business presses the button, and the result is checked against the account before anyone saves it.', 'AI drafts, a person confirms'],
  ['Reading a tender', 'Turns pasted tender text into requirements. Every value is checked against fixed lists, so it can at worst produce an empty or wrong draft.', 'AI drafts, a person confirms'],
  ['Meaning check', 'Compares what an opportunity says with what a business does, by meaning. It sees no name, no ownership and no size, and sits beside the score.', 'Advisory only'],
  ['Summarising feedback', 'Condenses buyer ratings and comments into two or three sentences, using only what was written.', 'Advisory only'],
  ['Plain-language match note', 'Writes the paragraph that explains a match, from the stored figures. A template is used when the AI is unavailable.', 'Wording only'],
]
const NOT_AI = ['Fit and readiness scores', 'Whether a business passes a hard requirement', 'The ranked shortlist', 'Who is shortlisted or awarded', 'Who a document check flags']

function Pct({ v }: { v: number }) { return <span className="mono">{(v * 100).toFixed(0)}%</span> }

/** Public and live: the numbers below are computed when you open the page, from code you can rerun. */
export default function ResponsibleAI() {
  const ev = useLoad(() => api.evaluation())
  const e = ev.data
  return (
    <>
      <header className="topbar"><Link to="/"><Logo /></Link><div className="top-actions"><Link className="btn btn-outline" to="/">Back</Link></div></header>
      <article className="rai">
        <p className="eyebrow">Responsible AI</p>
        <h1>What the AI does here, what it never does, and how we check</h1>
        <p className="lead">Kopano Match ranks. A person decides. The scores are fixed rules you can read on every match, so a decision that affects a small business can always be explained and challenged.</p>

        <h2>Where AI is used, and where it is not</h2>
        <div className="rai-grid">
          <div>
            <h3>AI helps with</h3>
            {USES.map(([t, d, tag]) => (
              <div key={t} className="rai-card"><div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}><b>{t}</b><Badge tone="purple">{tag}</Badge></div><p>{d}</p></div>))}
          </div>
          <div>
            <h3>AI never touches</h3>
            <div className="rai-card dark">{NOT_AI.map((x) => <div key={x} className="metric-row"><span>{x}</span><Badge tone="green">Rules only</Badge></div>)}
              <p style={{ marginBottom: 0 }}>There is no model in the scoring path. Two runs on the same data give the same result, which is tested.</p></div>
          </div>
        </div>

        <h2>How we measure it</h2>
        {ev.error && <p className="callout red">{ev.error}</p>}
        {!e && !ev.error && <Spinner />}
        {e && (
          <>
            <p>Computed live on {e.data.businesses} synthetic businesses and {e.data.opportunities} opportunities. {e.data.source}. It holds no personal data. Rerun it yourself with <code>python scripts/evaluate_engine.py</code>.</p>
            <div className="rai-stats">
              <div><b>{e.scenarios.passed}/{e.scenarios.total}</b><span>planted scenarios behave as promised</span></div>
              <div><b>{e.determinism.identical ? 'Identical' : 'Differs'}</b><span>result on {e.determinism.runs} runs (fingerprint {e.determinism.fingerprint})</span></div>
              <div><b>{e.fairness.scores_changed_by_ownership}/{e.fairness.counterfactual_pairs}</b><span>scores changed when ownership was flipped</span></div>
            </div>

            <h3>Ranking quality</h3>
            <div className="table-wrap"><table>
              <thead><tr><th>Method</th><th>NDCG@5</th><th>Precision@3</th></tr></thead>
              <tbody>{e.benchmark.methods.map((m, i) => (
                <tr key={m.method} style={i === 0 ? { background: '#faf5ff' } : undefined}><td><b>{m.method}</b></td><td className="mono">{m.ndcg_at_5.toFixed(3)}</td><td className="mono">{m.precision_at_3.toFixed(3)}</td></tr>))}</tbody>
            </table></div>
            <p className="hint">{e.benchmark.rubric} The engine matches fit-only ranking on NDCG and does better on precision, because it also accounts for readiness. {e.benchmark.relevant_excluded_by_gates} of {e.benchmark.relevant_pairs} relevant pairs were removed by a hard requirement; that is the cost of hard gates, and it is shown here instead of hidden.</p>

            <h3>Fairness audit</h3>
            <p>Ownership is never an input to fit or readiness unless a buyer sets a transformation preference. We prove it by flipping every business's ownership across {e.fairness.counterfactual_pairs} neutral pairs: {e.fairness.scores_changed_by_ownership} scores changed. When a buyer does set a preference, it can move fit by at most {e.fairness.disclosed_max_fit_effect} points, and it is shown on the match.</p>
            <div className="table-wrap"><table>
              <thead><tr><th>Group</th><th>Businesses</th><th>Matched (not excluded)</th><th>Award ready</th></tr></thead>
              <tbody>{e.fairness.groups.map((g) => <tr key={g.group}><td>{g.group}</td><td>{g.businesses}</td><td><Pct v={g.kept_rate} /></td><td><Pct v={g.award_ready_rate} /></td></tr>)}</tbody>
            </table></div>
            <div className="rai-stats" style={{ marginTop: 14 }}>
              {e.fairness.disparate_impact.map((d) => (
                <div key={d.attribute}><b>{d.ratio.toFixed(2)}</b><span>{d.attribute}: {d.within_four_fifths ? 'within' : 'OUTSIDE'} the four-fifths rule</span></div>))}
            </div>
            <p className="hint">{e.fairness.note}</p>

            <h2>Human oversight</h2>
            <ul>{e.human_oversight.map((x) => <li key={x}>{x}</li>)}</ul>

            <h2>Limits we state openly</h2>
            <ul>{e.limitations.map((x) => <li key={x}>{x}</li>)}</ul>
          </>
        )}

        <h2>Your data</h2>
        <p>Sending a document to the AI reader is a choice made per document, shown before it happens and written to the audit log. Selfies and identity images are never stored. See the <Link to="/privacy">privacy notice</Link>. This pilot is built against POPIA's conditions; it is not claimed to be compliant.</p>
      </article>
    </>
  )
}
