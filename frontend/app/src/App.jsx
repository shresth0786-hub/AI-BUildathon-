import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts'
import { api, getToken, setToken } from './api.js'
import AdminRagPanel from './components/AdminRagPanel.jsx'
import Login from './components/Login.jsx'
import UserDatabasePanel from './components/UserDatabasePanel.jsx'
import CustomerCarePanel from './components/CustomerCarePanel.jsx'

// ------------------------------------------------------------------ colors
const C = { green: '#00b894', amber: '#fdcb6e', red: '#ff7675', accent: '#6c5ce7', blue: '#74b9ff' }

// ------------------------------------------------------------------ hooks
function useCountUp(target, dur = 900) {
  const [val, setVal] = useState(0)
  const prev = useRef(0)
  useEffect(() => {
    const from = prev.current
    const start = performance.now()
    let raf
    const step = (now) => {
      const p = Math.min(1, (now - start) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      setVal(from + (target - from) * eased)
      if (p < 1) raf = requestAnimationFrame(step)
      else prev.current = target
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, dur])
  return val
}

function useScrollSpy(ids) {
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    const onScroll = () => {
      let cur = ids[0]
      for (const id of ids) {
        const el = document.getElementById(id)
        if (el && el.getBoundingClientRect().top <= 120) cur = id
      }
      setActive(cur)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [ids])
  return active
}

function sortRows(rows, key, dir) {
  if (!key) return rows
  return [...rows].sort((a, b) => {
    const av = a[key]; const bv = b[key]
    if (av == null) return 1
    if (bv == null) return -1
    const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
    return dir === 'asc' ? cmp : -cmp
  })
}

function matches(rows, q) {
  if (!q) return rows
  const s = q.toLowerCase()
  return rows.filter((r) =>
    [r.user_id, r.merchant, r.decision, r.fraud_vector, r.event_id, r.name, r.phone]
      .some((v) => v && String(v).toLowerCase().includes(s)))
}

export function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem('sentinel_theme') || 'dark')
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('sentinel_theme', theme)
  }, [theme])
  const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])
  return [theme, toggleTheme]
}

// ------------------------------------------------------------------ basic UI
function Badge({ decision }) {
  return <span className={`badge ${decision}`}>{decision.toUpperCase()}</span>
}

function Stat({ label, value, sub, cls = '' }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={`value count-up ${cls}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

function AnimatedStat({ label, num, format, sub, cls = '' }) {
  const v = useCountUp(num)
  return (
    <Stat label={label}
      value={format ? format(v) : Math.round(v).toLocaleString()}
      sub={sub} cls={cls} />
  )
}

// ------------------------------------------------------------------ collapsible section
function Section({ id, title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div id={id} className="section-block" style={{ scrollMarginTop: 20 }}>
      <h2 className={`section section-head ${open ? 'open' : ''}`} onClick={() => setOpen((o) => !o)}>
        <span className="chev">▶</span>{title}
        <span className="muted" style={{ fontSize: 11, fontWeight: 400, marginLeft: 6 }}>{open ? '· click to collapse' : '· collapsed · click'}</span>
      </h2>
      <div className={`section-body ${open ? '' : 'collapsed'}`}>{children}</div>
    </div>
  )
}

// ------------------------------------------------------------------ pie
function DecisionPie({ metrics }) {
  const data = [
    { name: 'Approved', value: metrics.approve, color: C.green },
    { name: 'Pending (review band)', value: metrics.review, color: C.amber },
    { name: 'Blocked', value: metrics.block, color: C.red },
  ]
  return (
    <div className="card">
      <h3>Decision distribution</h3>
      <ResponsiveContainer width="100%" height={215}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55}
            outerRadius={85} paddingAngle={2}>
            {data.map((d) => <Cell key={d.name} fill={d.color} />)}
          </Pie>
          <Tooltip contentStyle={{ background: 'var(--card-2)', border: '1px solid var(--border)', borderRadius: 10 }} />
          <Legend formatter={(v) => <span style={{ color: 'var(--muted)' }}>{v}</span>} />
        </PieChart>
      </ResponsiveContainer>
      <div className="grid grid-3" style={{ marginTop: 8 }}>
        <div className="score-box"><div className="m green">Approved</div><div className="p">{metrics.approve}</div></div>
        <div className="score-box"><div className="m amber">Pending</div><div className="p">{metrics.review}</div></div>
        <div className="score-box"><div className="m red">Blocked</div><div className="p">{metrics.block}</div></div>
      </div>
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
          <Tooltip contentStyle={{ background: 'var(--card-2)', border: '1px solid var(--border)', borderRadius: 10 }} />
          <Bar dataKey="w" name="coef" radius={[0, 6, 6, 0]}>
            {data.map((d, i) => <Cell key={i} fill={[C.accent, C.accent2 ?? C.blue, C.blue][i]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ------------------------------------------------------------------ sortable header helper
function SortableTh({ label, k, sortKey, sortDir, onSort }) {
  const active = sortKey === k
  return (
    <th className="sortable" onClick={() => onSort(k)}>
      {label}
      {active && <span className="sort-arrow">{sortDir === 'asc' ? '▲' : '▼'}</span>}
    </th>
  )
}

// ------------------------------------------------------------------ logic for both stream tables
function useStreamTable(rows) {
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState('')
  const [sortDir, setSortDir] = useState('desc')
  const onSort = (k) => {
    if (sortKey === k) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(k); setSortDir('asc') }
  }
  const filtered = matches(rows, q)
  const sorted = sortRows(filtered, sortKey, sortDir)
  return { q, setQ, sortKey, sortDir, onSort, rows: sorted }
}

function EventRows({ rows, onSelect, onRisk }) {
  return rows.map((r) => {
    const riskColor = r.p_investigator > 0.6 ? C.red : r.p_investigator > 0.35 ? C.amber : C.green
    return (
      <tr className={onSelect ? 'clickable' : ''} key={r.event_id}
        onClick={onSelect ? () => onSelect(r.event_id) : undefined}>
        <td className="mono">{r.event_id.slice(0, 18)}</td>
        <td>{r.user_id}</td>
        <td>{r.merchant}</td>
        <td>₹{r.amount_inr.toLocaleString('en-IN')}</td>
        <td style={{ color: riskColor }}>{(r.p_investigator * 100).toFixed(1)}%</td>
        <td><Badge decision={r.decision} /></td>
        <td className="muted">{r.fraud_vector ? r.fraud_vector.replace(/_/g, ' ') : '—'}</td>
        {onRisk !== undefined && (
          <td className="muted" style={{ fontSize: 12 }}>{onRisk}</td>
        )}
      </tr>
    )
  })
}

function StreamToolbar({ q, setQ, placeholder }) {
  return (
    <div className="table-toolbar">
      <input className="search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder || 'Search users, merchants, decisions…'} />
    </div>
  )
}

// ------------------------------------------------------------------ table
function EventsTable({ onSelect }) {
  const [risk, setRisk] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const { q, setQ, sortKey, sortDir, onSort, rows: view } = useStreamTable(rows)

  useEffect(() => {
    setLoading(true)
    api.events(risk, 250).then(setRows).catch(() => setRows([])).finally(() => setLoading(false))
  }, [risk])

  const viewWithRisk = view.map((r) => ({ ...r, _risk: risk || 'all' }))

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>Recent payments (top risk)</h3>
        <select value={risk} onChange={(e) => setRisk(e.target.value)} style={{ width: 160 }}>
          <option value="">All</option>
          <option value="approve">Approved</option>
          <option value="review">Review</option>
          <option value="block">Blocked</option>
        </select>
      </div>
      <StreamToolbar q={q} setQ={setQ} placeholder="Search this stream… (e.g. a merchant or user)" />
      <p className="muted" style={{ fontSize: 12, margin: '0 0 8px' }}>
        Click a row to open the interactive investigation report. Click a column header to sort.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th className="sortable" onClick={() => onSort('event_id')}>Event{sortKey === 'event_id' && <span className="sort-arrow">{sortDir === 'asc' ? '▲' : '▼'}</span>}</th>
              <SortableTh label="User" k="user_id" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Merchant" k="merchant" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Amount" k="amount_inr" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th>Risk</th>
              <SortableTh label="Decision" k="decision" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th>Vector</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="muted">Loading…</td></tr>}
            {!loading && viewWithRisk.length === 0 && <tr><td colSpan={7} className="muted">No events match.</td></tr>}
            <EventRows rows={viewWithRisk} onSelect={onSelect} />
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ detail
function Gauge({ label, pct, color }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div className="gauge-ring" style={{ '--p': Math.round(pct * 100), '--ring': color, margin: '0 auto' }}>
        <span className="gauge-val">{(pct * 100).toFixed(0)}%</span>
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{label}</div>
    </div>
  )
}

function EventDetail({ id, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    api.event(id).then(setD).catch((e) => setErr(e.message))
  }, [id])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(d.report || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable */ }
  }

  const decisionColor = d?.decision === 'block' ? C.red : d?.decision === 'review' ? C.amber : C.green

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Investigation Report</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn ghost" onClick={copy} title="Copy the full report to the clipboard">
              {copied ? 'Copied ✓' : 'Copy report'}
            </button>
            <button className="btn ghost" onClick={onClose}>Close</button>
          </div>
        </div>
        {err && <p className="red" style={{ color: C.red }}>Error: {err}</p>}
        {!err && !d && <p className="muted">Loading…</p>}
        {d && (
          <>
            <div className="spacer" />
            <div className="grid grid-4">
              <Gauge label="ML Risk" pct={d.scores.ml_risk} color={C.green} />
              <Gauge label="Behaviour AI" pct={d.scores.behaviour_ai} color={C.blue} />
              <Gauge label="Graph Engine" pct={d.scores.graph_engine} color={C.amber} />
              <Gauge label="Investigator" pct={d.scores.investigator} color={C.accent} />
            </div>
            <div className="grid grid-2" style={{ marginTop: 16 }}>
              <div className="score-box" style={{ borderColor: decisionColor }}>
                <div className="m">Combined decision</div>
                <div className="p" style={{ color: decisionColor }}>{d.decision.toUpperCase()}</div>
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
            <h3 style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--text)' }}>Evidence — why this verdict</h3>
            {d.evidence.length > 0 ? (
              d.evidence.map((e, i) => (
                <div key={i} className={`evidence-card model-${e.model}`}>
                  <div className="ec-head">Step {i + 1} · {e.model.replace(/_/g, ' ')} · {e.signal}</div>
                  <div style={{ fontSize: 13 }}>{e.detail}</div>
                  {typeof e.weight === 'number' && (
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>weight: {(e.weight * 100).toFixed(1)}%</div>
                  )}
                </div>
              ))
            ) : (
              <div className="muted" style={{ fontSize: 13 }}>No evidence raised.</div>
            )}
            <div className="spacer" />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--text)' }}>Full report</h3>
            </div>
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
        {pv.channel === 'sms' ? '✉️' : pv.channel === 'whatsapp' ? '💬' : '📞'}{' '}
        Payment confirmation — {pv.channel === 'call' ? 'phone call' : pv.channel === 'sms' ? 'SMS' : 'WhatsApp'}
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
        <summary className="muted" style={{ cursor: 'pointer', fontSize: 13 }}>
          {pv.channel === 'call' ? 'Call script (agent reads this)' : 'OTP message / delivery script'}
        </summary>
        {(pv.call_script || []).map((line, i) => <div key={i} className="muted" style={{ fontSize: 13, marginTop: 4 }}>• {line}</div>)}
      </details>
      {(pv.delivered || pv.delivery_sid || pv.recording_available) && (
        <div className="rec-log" style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            Delivery — {pv.channel === 'call' ? 'phone call' : pv.channel === 'sms' ? 'SMS' : 'WhatsApp'}
          </div>
          <div className="muted" style={{ fontSize: 13 }}>
            Status: <b>{pv.delivered || '—'}</b>
            {pv.message && pv.channel !== 'call' && <> · via Twilio {pv.message}</>}
            {pv.delivery_sid && <> · SID <span className="mono">{pv.delivery_sid}</span></>}
            {pv.created_at && <> · <span className="mono">{new Date(pv.created_at * 1000).toLocaleString()}</span></>}
          </div>
          {pv.recording_available && pv.channel === 'call' && pv.delivery_sid && (
            <div style={{ fontSize: 13, marginTop: 4 }}>
              <span className="pill online">Recording enabled</span>{' '}
              <a className="muted" style={{ textDecoration: 'underline' }} target="_blank" rel="noreferrer"
                href={`https://console.twilio.com/us1/develop/voice/manage/recordings?sid=${pv.delivery_sid}`}>
                View audio in Twilio →
              </a>
            </div>
          )}
        </div>
      )}
      {pv.status === 'approved' && <div className="green" style={{ marginTop: 8 }}>Payer confirmed ownership — payment approved.</div>}
      {pv.status === 'blocked' && <div className="red" style={{ marginTop: 8 }}>Verification failed — payment blocked: {pv.reason || 'caller denied'}</div>}
    </div>
  )
}

function PhoneVerificationPanel({ sessions, mode, onChange }) {
  const [busyId, setBusyId] = useState(null)
  const [err, setErr] = useState(null)

  const act = async (id, action, otp) => {
    setErr(null); setBusyId(id)
    try {
      if (action === 'confirm') await api.verConfirm(id, otp)
      else if (action === 'resend') await api.verResend(id)
      else await api.verDeny(id)
      onChange && onChange()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card">
      <h3>OTP payment confirmations</h3>
      <div className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Mode: <b>{mode}</b> — medium-risk payments are held for an OTP
        (call/SMS/WhatsApp) before settlement. Run the <b>Borderline</b> scenario
        above to open a session.
      </div>
      {err && <p style={{ color: C.red, fontSize: 13 }}>{err}</p>}
      {sessions.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No verification sessions yet.</div>}
      {sessions.map((pv) => (
        <PhoneVerifyBox key={pv.verification_id} pv={pv}
          busy={busyId === pv.verification_id} onAction={(a) => act(pv.verification_id, a, pv.otp)} />
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ live test
function LiveTest({ onInvestigate }) {
  const [running, setRunning] = useState(false)
  const [mode, setMode] = useState('fraud')
  const [phone, setPhone] = useState(import.meta.env.VITE_DEMO_PHONE || '')
  const [channel, setChannel] = useState('call')
  const [out, setOut] = useState(null)
  const [err, setErr] = useState(null)

  const run = async () => {
    setRunning(true); setErr(null); setOut(null)
    try {
      const body = mode === 'fraud' ? await api.demoFraud()
        : mode === 'review' ? await api.demoBorderline(phone, channel) : await api.demoClean()
      const res = await api.investigate(body)
      setOut(res)
      if (onInvestigate) onInvestigate(res)
    } catch (e) {
      setErr(e.message)
    } finally {
      setRunning(false)
    }
  }

  const [pvBusy, setPvBusy] = useState(false)
  const [corrMsg, setCorrMsg] = useState(null)
  const correct = async (isFraud) => {
    if (!out?.event_id) return
    setErr(null); setCorrMsg(null)
    try {
      const r = await api.correct(out.event_id, isFraud)
      setCorrMsg(`Learned: marked as ${isFraud ? 'fraud' : 'clean'} (${r.label === 1 ? 'fraud' : 'clean'}).`)
      if (onInvestigate) onInvestigate({ ...out, decision: isFraud ? 'block' : 'approve', _message: `Marked ${isFraud ? 'fraud (blocked)' : 'clean (approved)'}` })
    } catch (e) {
      setErr(e.message)
    }
  }
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
      if (onInvestigate && updated) onInvestigate({ ...out, decision: updated.status, phone_verification: updated })
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
            <label title="Twilio will reach this number on the chosen channel">Payer number</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)}
              placeholder="+91XXXXXXXXXX" />
          </div>
        )}
        {mode === 'review' && (
          <div>
            <label>OTP channel</label>
            <select value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="call">Phone call</option>
              <option value="sms">SMS</option>
              <option value="whatsapp">WhatsApp</option>
            </select>
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
            <div style={{ marginTop: 10 }}>
              {out.evidence.map((e, i) => (
                <div key={i} className={`evidence-card model-${e.model}`}>
                  <div className="ec-head">{e.model.replace(/_/g, ' ')} · {e.signal}</div>
                  <div style={{ fontSize: 13 }}>{e.detail}</div>
                </div>
              ))}
            </div>
          )}
          <div className="form-row" style={{ marginTop: 10 }}>
            <span className="muted" style={{ fontSize: 13 }}>Was this decision right?</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn" onClick={() => correct(false)} title="This was clean — correct the model">Mark clean</button>
              <button className="btn danger" onClick={() => correct(true)} title="This was fraud — correct the model">Mark fraud</button>
            </div>
          </div>
          {corrMsg && <div className="green" style={{ fontSize: 13, marginTop: 8 }}>{corrMsg}</div>}
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

// ------------------------------------------------------------------ recent transactions
function RecentTransactions({ onAlert }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const seen = useRef(new Set())
  const { q, setQ, sortKey, sortDir, onSort, rows: view } = useStreamTable(rows)

  const load = useCallback(() => {
    setLoading(true)
    api.events('', 100).then((list) => {
      setRows(list)
      list.forEach((r) => {
        if (!seen.current.has(r.event_id)) {
          seen.current.add(r.event_id)
          if (onAlert && (r.decision === 'block' || r.decision === 'review')) {
            onAlert(
              r.decision === 'block' ? 'Payment blocked' : 'Payment flagged for review',
              `${r.user_id} · ₹${r.amount_inr.toLocaleString('en-IN')} at ${r.merchant} (${(r.p_investigator * 100).toFixed(0)}% risk)`,
              r.decision,
            )
          }
        }
      })
    }).catch(() => setRows([])).finally(() => setLoading(false))
  }, [onAlert])
  useEffect(() => {
    load()
    const t = setInterval(load, 8000)
    return () => clearInterval(t)
  }, [load])

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Recent transactions <span className="live-dot" /></h3>
        <button className="btn ghost" onClick={load}>Refresh</button>
      </div>
      <div className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Latest scored payments in the stream (live).
      </div>
      <StreamToolbar q={q} setQ={setQ} placeholder="Search this stream…" />
      <div className="spacer" style={{ height: 10 }} />
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th className="sortable" onClick={() => onSort('event_id')}>Event{sortKey === 'event_id' && <span className="sort-arrow">{sortDir === 'asc' ? '▲' : '▼'}</span>}</th>
              <SortableTh label="User" k="user_id" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Merchant" k="merchant" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <SortableTh label="Amount" k="amount_inr" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th>Risk</th>
              <SortableTh label="Decision" k="decision" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th>Vector</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="muted">Loading…</td></tr>}
            {!loading && view.length === 0 && <tr><td colSpan={7} className="muted">No transactions yet.</td></tr>}
            {view.map((r) => {
              const riskColor = r.p_investigator > 0.6 ? C.red : r.p_investigator > 0.35 ? C.amber : C.green
              return (
                <tr key={r.event_id}>
                  <td className="mono">{r.event_id.slice(0, 18)}</td>
                  <td>{r.user_id}</td>
                  <td>{r.merchant}</td>
                  <td>₹{r.amount_inr.toLocaleString('en-IN')}</td>
                  <td style={{ color: riskColor }}>{(r.p_investigator * 100).toFixed(1)}%</td>
                  <td><Badge decision={r.decision} /></td>
                  <td className="muted">{r.fraud_vector ? r.fraud_vector.replace(/_/g, ' ') : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
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

// ------------------------------------------------------------------ continual learning
function LearningPanel({ onChanged }) {
  const [fb, setFb] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  const refresh = useCallback(() => {
    api.feedback().then(setFb).catch(() => {})
  }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  const retrain = async () => {
    setBusy(true); setMsg(null)
    try {
      const r = await api.retrain()
      setMsg(`Retrained on ${r.feedback_used} confirmed feedback transactions. AUC ${(r.investigator_auc * 100).toFixed(1)}%.`)
      refresh()
      onChanged && onChanged()
    } catch (e) {
      setMsg(`Retrain error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  const st = fb?.status
  const store = st?.store
  const corr = st?.corrector
  return (
    <div className="card">
      <h3>Continual learning</h3>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        The model learns from each transaction: phone-verification verdicts and manual
        corrections feed an <b>online correction layer</b> immediately, and are folded
        into the models on <b>retrain</b> — so past errors are not repeated.
      </p>
      <div className="grid grid-4">
        <div className="score-box">
          <div className="m">Recorded</div>
          <div className="p">{store?.total_recorded ?? 0}</div>
          <div className="muted" style={{ fontSize: 12 }}>scored transactions</div>
        </div>
        <div className="score-box">
          <div className="m">Labelled</div>
          <div className="p accent">{store?.labelled ?? 0}</div>
          <div className="muted" style={{ fontSize: 12 }}>confirmed ground truth</div>
        </div>
        <div className="score-box">
          <div className="m">Online updates</div>
          <div className="p">{corr?.updates ?? 0}</div>
          <div className="muted" style={{ fontSize: 12 }}>corrector steps</div>
        </div>
        <div className="score-box">
          <div className="m">Unlabelled</div>
          <div className="p">{store?.unlabelled ?? 0}</div>
          <div className="muted" style={{ fontSize: 12 }}>awaiting verdict</div>
        </div>
      </div>
      {store?.by_source && Object.keys(store.by_source).length > 0 && (
        <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          Labels by source: {Object.entries(store.by_source)
            .map(([k, v]) => `${k} ${v}`).join(' · ')}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
        <button className="btn" onClick={retrain} disabled={busy}>
          {busy ? 'Retraining…' : 'Trigger retrain'}
        </button>
        {msg && <span style={{ fontSize: 13 }}>{msg}</span>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ app
export default function App() {
  const [session, setSession] = useState(null)
  const [summary, setSummary] = useState(null)
  const [vectors, setVectors] = useState(null)
  const [rzp, setRzp] = useState(null)
  const [tm, setTm] = useState(null)
  const [selected, setSelected] = useState(null)
  const [verSessions, setVerSessions] = useState([])
  const [verMode, setVerMode] = useState('simulated')
  const [ragOpen, setRagOpen] = useState(false)
  const [theme, toggleTheme] = useTheme()

  const [toasts, setToasts] = useState([])
  const addToast = useCallback((title, msg, kind) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, title, msg, kind: kind || 'approve' }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000)
  }, [])
  const dismissToast = (id) => setToasts((t) => t.filter((x) => x.id !== id))

  const isAdmin = session?.role === 'admin'
  const isCare = session?.role === 'customer_care'

  const logout = () => {
    setToken(null); setSession(null)
  }

  useEffect(() => {
    if (!getToken()) { setSession(null); return }
    api.me().then(setSession).catch(() => { setToken(null); setSession(null) })
  }, [])

  const refreshVer = useCallback(() => {
    api.verification().then((d) => {
      setVerSessions(d.sessions || [])
      setVerMode(d.status?.mode || 'simulated')
    }).catch(() => {})
  }, [])

  const load = useCallback(() => {
    Promise.all([api.summary(), api.vectors(), api.rzpStatus(), api.testMetrics()])
      .then(([s, v, r, t]) => { setSummary(s); setVectors(v); setRzp(r); setTm(t) })
      .catch(() => {})
    refreshVer()
  }, [refreshVer])
  useEffect(load, [load])

  const NAV = [
    { id: 'userdb', label: 'User database' },
    { id: 'stream', label: 'Recent transactions' },
    { id: 'overview', label: 'Overview' },
    { id: 'metrics', label: 'Track 02 metrics' },
    { id: 'vectors', label: 'Fraud vectors' },
    { id: 'phone', label: 'Phone verification' },
    { id: 'learning', label: 'Continual learning' },
    { id: 'queries', label: 'Customer-care queries' },
    { id: 'events', label: 'Payment stream' },
  ]
  const active = useScrollSpy(NAV.map((n) => n.id))
  const goto = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

  if (!session) {
    return <Login onSuccess={(s) => { setToken(s.token); setSession(s) }} />
  }

  const metrics = summary?.decision_metrics
  const roleLabel = session.role_label || session.role

  const onInvestigate = (res) => {
    const dec = res?.decision
    if (!dec) return
    const person = res?.user_id || 'a payer'
    const amt = res?.amount_inr
    const label = amt ? `${person} · ₹${Number(amt).toLocaleString('en-IN')}` : person
    if (dec === 'block') addToast('Payment blocked', `${label} declined — high fraud risk.`, 'block')
    else if (dec === 'review') addToast('Flagged for review', `${label} held for phone confirmation.`, 'review')
    else if (dec === 'approve') addToast('Payment approved', `${label} cleared.`, 'approve')
  }

  return (
    <div className="wrap">
      <header>
        <div className="logo">🛡</div>
        <div>
          <h1>Sentinel AI</h1>
          <p>Razorpay Fraud Guardian · ML Risk · Behaviour AI · Graph Engine → AI Investigator</p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="theme-toggle" onClick={toggleTheme} title="Toggle dark / light theme">
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <span className="pill">{session.name} · {roleLabel}</span>
          <button className="btn" onClick={() => setRagOpen(true)} style={{ padding: '8px 12px' }}>
            🤖 SENbot
          </button>
          {rzp && <span className={`pill ${rzp.configured ? 'online' : ''}`}>
            {rzp.configured ? 'Razorpay test-mode: ' + (rzp.live ? 'LIVE ⚠' : 'configured') : 'Keyless demo'}
          </span>}
          <button className="btn ghost" onClick={logout}>Log out</button>
        </div>
      </header>

      <div className="app-grid">
        <aside className="side-nav">
          {NAV.filter((n) => (n.id === 'userdb' ? isAdmin : n.id === 'queries' ? (isAdmin || isCare) : true))
            .map((n) => (
              <a key={n.id} className={active === n.id ? 'active' : ''} onClick={() => goto(n.id)}>{n.label}</a>
            ))}
        </aside>

        <div className="app-main">
          {isAdmin && (
            <div id="userdb" className="section-block" style={{ scrollMarginTop: 20 }}>
              <UserDatabasePanel />
            </div>
          )}

          <div id="stream" className="section-block" style={{ scrollMarginTop: 20 }}>
            <RecentTransactions onAlert={onInvestigate} />
          </div>

          <Section id="overview" title="Overview">
            <div className="grid grid-4">
              <AnimatedStat label="Payments analysed" num={summary?.n_events ?? 0} sub="synthetic Razorpay-style events" />
              <AnimatedStat label="Fraud rate" num={summary ? summary.fraud_rate * 100 : 0} format={(v) => v.toFixed(1) + '%'} sub={`${summary?.n_fraud ?? '—'} fraudulent events`} cls="red" />
              <AnimatedStat label="Investigator AUC" num={summary ? summary.investigator_auc : 0} format={(v) => v.toFixed(3)} sub={`ML AUC ${summary?.ml_auc?.toFixed(3) ?? '—'}`} cls="accent" />
              <AnimatedStat label="Leakage" num={metrics ? metrics.leakage * 100 : 0} format={(v) => v.toFixed(1) + '%'} sub={`${metrics?.fraud_caught ?? '—'}/${metrics?.fraud_total ?? '—'} fraud caught`} cls="amber" />
            </div>
            <div className="spacer" />
            <div className="grid grid-2">
              {metrics && <DecisionPie metrics={metrics} />}
              {summary && <ModelScores weights={summary.weights} />}
            </div>
          </Section>

          <div id="metrics" className="section-block" style={{ scrollMarginTop: 20 }}>
            <h2 className="section">Track 02 — AI Risk Manager: the bar</h2>
            <TestMetrics t={tm} />
          </div>

          <Section id="vectors" title="Fraud vectors & live check">
            <div className="grid grid-2">
              {vectors && <VectorBars vectors={vectors} />}
              <LiveTest key={summary ? 'loaded' : 'loading'} onInvestigate={onInvestigate} />
            </div>
          </Section>

          <Section id="phone" title="OTP payment confirmation (call / SMS / WhatsApp · review band)">
            <PhoneVerificationPanel sessions={verSessions} mode={verMode} onChange={refreshVer} />
          </Section>

          {!isCare && (
            <Section id="learning" title="Continual learning">
              <LearningPanel />
            </Section>
          )}

          {(isAdmin || isCare) && (
            <Section id="queries" title="Customer-care queries">
              <CustomerCarePanel />
            </Section>
          )}

          <Section id="events" title="Payment stream" defaultOpen={false}>
            <EventsTable onSelect={setSelected} />
          </Section>
        </div>
      </div>

      {selected && <EventDetail id={selected} onClose={() => setSelected(null)} />}

      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <span className="t-dot" />
            <div style={{ minWidth: 0 }}>
              <div className="t-title">{t.title}</div>
              {t.msg && <div className="t-msg">{t.msg}</div>}
            </div>
            <button className="t-close" onClick={() => dismissToast(t.id)} title="Dismiss">×</button>
          </div>
        ))}
      </div>

      <AdminRagPanel open={ragOpen} onClose={() => setRagOpen(false)}
        role={session?.role} isAdmin={isAdmin} isCare={isCare} />

      <div className="spacer" />
      <footer className="muted" style={{ fontSize: 12, textAlign: 'center' }}>
        Built for the buildathon — synthetic data (keyless) + optional Razorpay test-mode webhook ingestion.
      </footer>
    </div>
  )
}
