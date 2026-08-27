const BASE = '/api'

async function get(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.detail || `POST ${path} -> ${res.status}`)
  }
  return res.json()
}

export const api = {
  summary: () => get('/summary'),
  testMetrics: () => get('/test-metrics'),
  events: (risk, limit = 250) =>
    get(`/events${risk ? `?risk=${risk}` : ''}&limit=${limit}`),
  event: (id) => get(`/events/${id}`),
  vectors: () => get('/vectors'),
  rzpStatus: () => get('/rzp/status'),
  demoFraud: () => get('/demo/fraud'),
  demoClean: () => get('/demo/clean'),
  investigate: (body) => post('/investigate', body),
}
