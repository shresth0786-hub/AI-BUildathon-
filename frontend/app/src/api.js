const BASE = '/api'
const TOKEN_KEY = 'sentinel_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(extra = {}) {
  const t = getToken()
  return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...extra }
}

async function get(path) {
  const res = await fetch(BASE + path, { headers: authHeaders() })
  if (!res.ok) throw new Error(await errorText(res, `GET ${path} -> ${res.status}`))
  return res.json()
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorText(res, `POST ${path} -> ${res.status}`))
  return res.json()
}

async function patch(path, body) {
  const res = await fetch(BASE + path, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorText(res, `PATCH ${path} -> ${res.status}`))
  return res.json()
}

async function errorText(res, fallback) {
  try {
    const j = await res.json()
    return j?.detail || fallback
  } catch {
    return fallback
  }
}

export const api = {
  authRoles: () => get('/auth/roles'),
  login: (username, password) => post('/auth/login', { username, password }),
  me: () => get('/auth/me'),
  summary: () => get('/summary'),
  testMetrics: () => get('/test-metrics'),
  events: (risk, limit = 250) =>
    get(`/events?${risk ? `risk=${risk}&` : ''}limit=${limit}`),
  event: (id) => get(`/events/${id}`),
  vectors: () => get('/vectors'),
  rzpStatus: () => get('/rzp/status'),
  demoFraud: () => get('/demo/fraud'),
  demoClean: () => get('/demo/clean'),
  demoBorderline: (phone) => ({
    event: {
      user_id: 'usr_rev_demo',
      device_id: 'dev_new_demo',
      card_last4: '4411',
      amount_inr: 6000,
      merchant: 'TechNova Store',
      payment_method: 'card',
      card_bin_country: 'IN',
      ip_geo_match: true,
      is_international: false,
      billing_zip: '400001',
      shipping_zip: '560001',
      typing_seconds: 2.5,
      attempt_count: 2,
      is_new_device: true,
      three_ds_passed: true,
      status: 'captured',
      phone: phone || import.meta.env.VITE_DEMO_PHONE || '',
    },
    history: [],
  }),
  investigate: (body) => post('/investigate', body),
  verification: () => get('/verification'),
  verConfirm: (id, otp) => post(`/verification/${id}/confirm`, { otp }),
  verDeny: (id) => post(`/verification/${id}/deny`),
  verResend: (id) => post(`/verification/${id}/resend`),
  feedback: () => get('/feedback'),
  correct: (id, isFraud) => post(`/feedback/${id}/correct`, { is_fraud: isFraud }),
  retrain: () => post('/learning/retrain'),
  ragAsk: (question) => post('/rag/ask', { question }),
  ragKnowledge: () => get('/rag/knowledge'),
  ragStatus: () => get('/rag/status'),
  users: () => get('/users'),
  user: (id) => get(`/users/${id}`),
  queryCreate: (body) => post('/queries', body),
  queries: () => get('/queries'),
  queryUpdate: (id, body) => patch(`/queries/${id}`, body),
}
