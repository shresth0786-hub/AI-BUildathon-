import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts'
import { api } from './api.js'

// ------------------------------------------------------------------ colors
const C = { green: '#00b894', amber: '#fdcb6e', red: '#ff7675', accent: '#6c5ce7', blue: '#74b9ff' }

function Badge({ decision }) {
  return <span className={`badge ${decision}`}>{decision.toUpperCase()}</span>
}

// ------------------------------------------------------------------ cards
function Stat({ label, value, sub, cls = '' }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={`value ${cls}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

// ------------------------------------------------------------------ pie
function DecisionPie({ metrics }) {
  const data = [
    { name: 'Approved', value: metrics.approve, color: C.green },
    { name: 'Review', value: metrics.review, color: C.amber },
    { name: 'Blocked', value: metrics.block, color: C.red },
  ]
  return (
    <div className="card">
      <h3>Decision distribution</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55}
            outerRadius={85} paddingAngle={2}>
            {data.map((d) => <Cell key={d.name} fill={d.color} />)}
          </Pie>
          <Tooltip contentStyle={{ background: '#151d30', border: '1px solid #24304d', borderRadius: 10 }} />
          <Legend formatter={(v) => <span style={{ color: '#8b98b8' }}>{v}</span>} />
        </PieChart>
      </ResponsiveContainer>
      <div className="muted" style={{ fontSize: 13 }}>
        {metrics.fraud_caught}/{metrics.fraud_total} fraud caught ·{' '}
        {metrics.false_alarms} false alarms · leakage {(metrics.leakage * 100).toFixed(1)}%
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ vectors
function VectorBars({ vectors }) {
  const data = Object.entries(vectors.vectors || {}).map(([k, v]) => ({
    name: k.replace(/_/g, ' '), value: v,
  }))
  return (
    <div className="card">
      <h3>Fraud vectors detected</h3>
      {data.map((d) => (
        <div className="bar-row" key={d.name}>
          <span className="name">{d.name}</span>
          <span className="bar">
            <span className="fill" style={{ width: `${(d.value / data[0].value) * 100}%`,
              background: 'linear-gradient(90deg,#6c5ce7,#00cec9)' }} />
          </span>
          <span className="val">{d.value}</span>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>{vectors.total_fraud} total fraudulent events labelled</div>
    </div>
  )
}

// ------------------------------------------------------------------ scores
function ModelScores({ weights }) {
  const data = [
    { name: 'ML Risk', w: weights?.ml_risk ?? 0 },
    { name: 'Behaviour AI', w: weights?.behaviour_ai ?? 0 },
    { name: 'Graph Engine', w: weights?.graph_engine ?? 0 },
  ]
  return (
    <div className="card">
      <h3>Investigator ensemble weights</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 20, right: 20 }}>
          <CartesianGrid stroke="#1c2640" horizontal={false} />
          <XAxis type="number" stroke="#8b98b8" />
          <YAxis type="category" dataKey="name" stroke="#8b98b8" width={90} />
          <Tooltip contentStyle={{ background: '#151d30', border: '1px solid #24304d', borderRadius: 10 }} />
          <Bar dataKey="w" name="coef" radius={[0, 6, 6, 0]}>
            {data.map((d, i) => <Cell key={i} fill={[C.accent, C.accent2 ?? C.blue, C.blue][i]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ------------------------------------------------------------------ table
function EventsTable({ onSelect }) {
  const [risk, setRisk] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.events(risk, 250).then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [risk])

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Recent payments (top risk)</h3>
        <select value={risk} onChange={(e) => setRisk(e.target.value)} style={{ width: 160 }}>
          <option value="">All</option>
          <option value="approve">Approved</option>
          <option value="review">Review</option>
          <option value="block">Blocked</option>
        </select>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr><th>Event</th><th>User</th><th>Merchant</th><th>Amount</th><th>Risk</th><th>Decision</th><th>Vector</th></tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="muted">Loading…</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={7} className="muted">No events</td></tr>}
            {rows.map((r) => (
              <tr className="clickable" key={r.event_id} onClick={() => onSelect(r.event_id)}>
                <td className="mono">{r.event_id.slice(0, 18)}</td>
                <td>{r.user_id}</td>
                <td>{r.merchant}</td>
                <td>₹{r.amount_inr.toLocaleString('en-IN')}</td>
                <td style={{ color: r.p_investigator > 0.6 ? C.red : r.p_investigator > 0.35 ? C.amber : C.green }}>
                  {(r.p_investigator * 100).toFixed(1)}%
                </td>
                <td><Badge decision={r.decision} /></td>
                <td className="muted">{r.fraud_vector ? r.fraud_vector.replace(/_/g, ' ') : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ detail
function EventDetail({ id, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    api.event(id).then(setD).catch((e) => setErr(e.message))
  }, [id])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Investigation Report</h2>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
        {err && <p className="red" style={{ color: C.red }}>Error: {err}</p>}
        {!err && !d && <p className="muted">Loading…</p>}
        {d && (
          <>
            <div className="spacer" />
            <div className="grid grid-3">
              <div className="score-box"><div className="m">ML Risk</div><div className="p">{(d.scores.ml_risk * 100).toFixed(1)}%</div></div>
              <div className="score-box"><div className="m">Behaviour AI</div><div className="p">{(d.scores.behaviour_ai * 100).toFixed(1)}%</div></div>
              <div className="score-box"><div className="m">Graph Engine</div><div className="p">{(d.scores.graph_engine * 100).toFixed(1)}%</div></div>
            </div>
            <div className="grid grid-2" style={{ marginTop: 16 }}>
              <div className="score-box" style={{ borderColor: d.decision === 'block' ? C.red : d.decision === 'review' ? C.amber : C.green }}>
                <div className="m">Combined decision</div>
                <div className="p" style={{ color: d.decision === 'block' ? C.red : d.decision === 'review' ? C.amber : C.green }}>
                  {d.decision.toUpperCase()}
                </div>
                <div style={{ fontSize: 13 }}>₹{d.amount_inr.toLocaleString('en-IN')} · {d.merchant} · {d.user_id}</div>
              </div>
              <div className="score-box">
                <div className="m">Verdict</div>
                <div className="p accent">{(d.scores.investigator * 100).toFixed(1)}%</div>
                <div style={{ fontSize: 13 }} className="muted">
                  {d.true_label === 1 ? `Fraud vector: ${(d.fraud_vector || '').replace(/_/g, ' ')}` : 'No fraud label (synthetic clean)'}
                </div>
              </div>
            </div>
            <div className="spacer" />
            {d.evidence.length > 0 && (
              <ul className="evidence">
                {d.evidence.map((e, i) => (
                  <li key={i}>• <span className="tag">[{e.model}]</span> {e.detail}</li>
                ))}
              </ul>
            )}
            <div className="spacer" />
            <pre>{d.report}</pre>
          </>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ phone verification
function PhoneVerifyBox({ pv, busy, onAction }) {
  const approved = pv.status === 'approved'
  const blocked = pv.status === 'blocked' || pv.status === 'expired'
  return (
    <div className="phone-box" style={{ borderColor: approved ? C.green : blocked ? C.red : C.amber }}>
      <h4 style={{ margin: '0 0 6px', display: 'flex', alignItems: 'center', gap: 8 }}>
        📞 Phone-call payment confirmation
        <span className={`pill ${approved ? 'online' : blocked ? 'offline' : ''}`}>{pv.status.toUpperCase()}</span>
      </h4>
      <div className="muted" style={{ fontSize: 13 }}>
        ₹{pv.amount_inr?.toLocaleString('en-IN')} at {pv.merchant} · card ••{pv.card_last4} · call {pv.phone}
      </div>
      {pv.status === 'pending' && (
        <div className="form-row" style={{ marginTop: 10 }}>
          <div>
            <label>OTP sent to payer</label>
            <div className="mono otp">{pv.otp}</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <button className="btn" disabled={busy} onClick={() => onAction('confirm')}
              title="Payer read back the correct OTP -> approve">Confirm OTP</button>
            <button className="btn ghost" disabled={busy} onClick={() => onAction('resend')}>Resend</button>
            <button className="btn danger" disabled={busy} onClick={() => onAction('deny')}>Deny</button>
          </div>
        </div>
      )}
      <details style={{ marginTop: 8 }}>
        <summary className="muted" style={{ cursor: 'pointer', fontSize: 13 }}>Call script (agent reads this)</summary>
        {(pv.call_script || []).map((line, i) => <div key={i} className="muted" style={{ fontSize: 13, marginTop: 4 }}>• {line}</div>)}
      </details>
      {pv.status === 'approved' && <div className="green" style={{ marginTop: 8 }}>Payer confirmed ownership — payment approved.</div>}
      {pv.status === 'blocked' && <div className="red" style={{ marginTop: 8 }}>Verification failed — payment blocked: {pv.reason || 'caller denied'}</div>}
    </div>
  )
}

function PhoneVerificationPanel() {
  const [sessions, setSessions] = useState([])
  const [mode, setMode] = useState('simulated')
  const [busyId, setBusyId] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(() => {
    api.verification().then((d) => {
      setSessions(d.sessions || [])
      setMode(d.status?.mode || 'simulated')
    }).catch(() => {})
  }, [])
  useEffect(refresh, [refresh])

  const act = async (id, action, otp) => {
    setErr(null); setBusyId(id)
    try {
      if (action === 'confirm') await api.verConfirm(id, otp)
      else if (action === 'resend') await api.verResend(id)
      else await api.verDeny(id)
      refresh()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card">
      <h3>Phone-call payment confirmations</h3>
      <div className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Mode: <b>{mode}</b> — medium-risk payments are held for an OTP/call before settlement.
        Run the <b>Borderline</b> scenario above to open a session.
      </div>
      {err && <p style={{ color: C.red, fontSize: 13 }}>{err}</p>}
      {sessions.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No verification sessions yet.</div>}
      {sessions.map((pv) => (
        <PhoneVerifyBox key={pv.verification_id} pv={pv}
          busy={busyId === pv.verification_id} onAction={(a) => act(pv.verification_id, a)} />
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ live test
function LiveTest({ onInvestigate }) {
  const [running, setRunning] = useState(false)
  const [mode, setMode] = useState('fraud')
  const [phone, setPhone] = useState(import.meta.env.VITE_DEMO_PHONE || '')
  const [out, setOut] = useState(null)
  const [err, setErr] = useState(null)

  const run = async () => {
    setRunning(true); setErr(null); setOut(null)
    try {
      const body = mode === 'fraud' ? await api.demoFraud()
        : mode === 'review' ? await api.demoBorderline(phone) : await api.demoClean()
      const res = await api.investigate(body)
      setOut(res)
    } catch (e) {
      setErr(e.message)
    } finally {
      setRunning(false)
    }
  }

  const [pvBusy, setPvBusy] = useState(false)
  const phoneAction = async (action) => {
    const pv = out?.phone_verification
    if (!pv) return
    setPvBusy(true); setErr(null)
    try {
      let updated
      if (action === 'confirm') updated = await api.verConfirm(pv.verification_id, pv.otp)
      else if (action === 'resend') updated = await api.verResend(pv.verification_id)
      else updated = await api.verDeny(pv.verification_id)
      setOut({ ...out, phone_verification: updated })
    } catch (e) {
      setErr(e.message)
    } finally {
      setPvBusy(false)
    }
  }

  return (
    <div className="card">
      <h3>Live fraud check</h3>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Score a payment against the trained model stack and get an investigation report.
      </p>
      <div className="form-row">
        <div>
          <label>Scenario</label>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="fraud">Card-testing burst (fraud)</option>
            <option value="review">Borderline — phone verify (review)</option>
            <option value="clean">Established customer (clean)</option>
          </select>
        </div>
        {mode === 'review' && (
          <div>
            <label title="Twilio will call this number in real mode">Call number (review)</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)}
              placeholder="+91XXXXXXXXXX" />
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <button className="btn" onClick={run} disabled={running} style={{ width: '100%' }}>
            {running ? 'Scoring…' : 'Investigate'}
          </button>
        </div>
      </div>
      {err && <p style={{ color: C.red, fontSize: 13 }}>{err}</p>}
      {out && (
        <div className="spacer" style={{ height: 14 }} />
        )}
      {out && (
        <div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <Badge decision={out.decision} />
            <span className="mono">{out.event_id} · ₹{out.amount_inr.toLocaleString('en-IN')} · {out.merchant}</span>
          </div>
          <div className="grid grid-4" style={{ marginTop: 12 }}>
            <div className="score-box"><div className="m">ML</div><div className="p">{(out.scores.ml_risk * 100).toFixed(0)}%</div></div>
            <div className="score-box"><div className="m">Behaviour</div><div className="p">{(out.scores.behaviour_ai * 100).toFixed(0)}%</div></div>
            <div className="score-box"><div className="m">Graph</div><div className="p">{(out.scores.graph_engine * 100).toFixed(0)}%</div></div>
            <div className="score-box"><div className="m">Investigator</div><div className="p accent">{(out.scores.investigator * 100).toFixed(0)}%</div></div>
          </div>
          {out.evidence.length > 0 && (
            <ul className="evidence">
              {out.evidence.map((e, i) => (
                <li key={i}>• <span className="tag">[{e.model}]</span> {e.detail}</li>
              ))}
            </ul>
          )}
          {out.phone_verification && <PhoneVerifyBox pv={out.phone_verification} busy={pvBusy} onAction={phoneAction} />}
          <details style={{ marginTop: 12 }}>
            <summary className="muted" style={{ cursor: 'pointer', fontSize: 13 }}>Show full report</summary>
            <pre style={{ marginTop: 8 }}>{out.report}</pre>
          </details>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ architecture
function Architecture() {
  const nodes = [
    'Razorpay Test Payments', 'Feature Engineering', 'ML Risk Model', 'Behaviour AI',
    'Graph Engine', 'AI Investigator', 'Decision + Evidence', 'React Dashboard',
  ]
  return (
    <div className="card">
      <h3>Architecture</h3>
      <div className="arch">
        {nodes.map((n, i) => (
          <span key={n} style={{ display: 'contents' }}>
            {i > 0 && <span className="arrow">→</span>}
            <span className={`node ${[3, 4].includes(i) ? 'hot' : ''}`}>{n}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ test metrics
function TestMetrics({ t }) {
  if (!t) return null
  const bars = [
    { name: 'Precision', v: t.precision, c: C.green },
    { name: 'Recall (fraud blocked)', v: t.recall_fraud_blocked, c: C.blue },
    { name: 'F1', v: t.f1, c: C.accent },
  ]
  return (
    <div className="card">
      <h3>Held-out test set — honest metrics</h3>
      <div className="grid grid-3">
        <div className="score-box"><div className="m">Test events</div><div className="p">{t.n_test}</div><div className="muted" style={{fontSize:12}}>{t.n_fraud_test} fraud · {t.n_legit_test} legit</div></div>
        <div className="score-box"><div className="m">False positives</div><div className="p" style={{color: t.false_positives === 0 ? C.green : C.red}}>{t.false_positives}</div><div className="muted" style={{fontSize:12}}>legit blocked/reviewed</div></div>
        <div className="score-box"><div className="m">False negatives</div><div className="p">{t.false_negatives}</div><div className="muted" style={{fontSize:12}}>fraud approved</div></div>
      </div>
      <div className="spacer" style={{ height: 10 }} />
      {bars.map((b) => (
        <div className="bar-row" key={b.name}>
          <span className="name">{b.name}</span>
          <span className="bar">
            <span className="fill" style={{ width: `${b.v * 100}%`, background: b.c }} />
          </span>
          <span className="val">{(b.v * 100).toFixed(1)}%</span>
        </div>
      ))}
      <div className="spacer" style={{ height: 10 }} />
      <div className="grid grid-3">
        <div className="score-box"><div className="m">False-positive cost</div><div className="p" style={{color: C.green}}>₹{t.false_positive_cost_inr.toLocaleString('en-IN')}</div></div>
        <div className="score-box"><div className="m">False-negative cost</div><div className="p">₹{t.false_negative_cost_inr.toLocaleString('en-IN')}</div></div>
        <div className="score-box"><div className="m">Money prevented</div><div className="p green">₹{t.money_prevented_inr.toLocaleString('en-IN')}</div></div>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
        vs. no-intervention baseline cost of ₹{t.no_intervention_cost_inr.toLocaleString('en-IN')} · avg fraud value ₹{t.avg_fraud_value_inr.toLocaleString('en-IN')}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ app
export default function App() {
  const [summary, setSummary] = useState(null)
  const [vectors, setVectors] = useState(null)
  const [rzp, setRzp] = useState(null)
  const [tm, setTm] = useState(null)
  const [selected, setSelected] = useState(null)

  const load = useCallback(() => {
    Promise.all([api.summary(), api.vectors(), api.rzpStatus(), api.testMetrics()])
      .then(([s, v, r, t]) => { setSummary(s); setVectors(v); setRzp(r); setTm(t) })
      .catch(() => {})
  }, [])
  useEffect(load, [load])

  const metrics = summary?.decision_metrics

  return (
    <div className="wrap">
      <header>
        <div className="logo">🛡</div>
        <div>
          <h1>Razorpay Fraud Guardian</h1>
          <p>ML Risk · Behaviour AI · Graph Engine → AI Investigator</p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {rzp && <span className={`pill ${rzp.configured ? 'online' : ''}`}>
            {rzp.configured ? 'Razorpay test-mode: ' + (rzp.live ? 'LIVE ⚠' : 'configured') : 'Keyless demo'}
          </span>}
          <span className="pill online">API online</span>
        </div>
      </header>

      <Architecture />

      <h2 className="section">Overview</h2>
      <div className="grid grid-4">
        <Stat label="Payments analysed" value={(summary?.n_events ?? '—').toLocaleString()} sub="synthetic Razorpay-style events" />
        <Stat label="Fraud rate" value={summary ? (summary.fraud_rate * 100).toFixed(1) + '%' : '—'} sub={`${summary?.n_fraud ?? '—'} fraudulent events`} cls="red" />
        <Stat label="Investigator AUC" value={summary ? summary.investigator_auc.toFixed(3) : '—'} sub={`ML AUC ${summary?.ml_auc?.toFixed(3) ?? '—'}`} cls="accent" />
        <Stat label="Leakage" value={metrics ? (metrics.leakage * 100).toFixed(1) + '%' : '—'} sub={`${metrics?.fraud_caught ?? '—'}/${metrics?.fraud_total ?? '—'} fraud caught`} cls="amber" />
      </div>

      <div className="spacer" />

      <div className="grid grid-2">
        {metrics && <DecisionPie metrics={metrics} />}
        {summary && <ModelScores weights={summary.weights} />}
      </div>

      <div className="spacer" />
      <h2 className="section">Track 02 — AI Risk Manager: the bar</h2>
      <TestMetrics t={tm} />

      <h2 className="section">Fraud vectors</h2>
      <div className="grid grid-2">
        {vectors && <VectorBars vectors={vectors} />}
        <LiveTest key={summary ? 'loaded' : 'loading'} />
      </div>

      <h2 className="section">Phone-call payment confirmation (review band)</h2>
      <PhoneVerificationPanel />

      <h2 className="section">Payment stream</h2>
      <EventsTable onSelect={setSelected} />

      {selected && <EventDetail id={selected} onClose={() => setSelected(null)} />}

      <div className="spacer" />
      <footer className="muted" style={{ fontSize: 12, textAlign: 'center' }}>
        Built for the buildathon — synthetic data (keyless) + optional Razorpay test-mode webhook ingestion.
      </footer>
    </div>
  )
}
