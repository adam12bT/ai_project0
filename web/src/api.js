const BASE = '/api'

async function jsonFetch(path, options) {
  const res = await fetch(`${BASE}${path}`, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = data.error || `Request failed (${res.status})`
    const err = new Error(msg)
    err.status = res.status
    err.payload = data
    throw err
  }
  return data
}

export function getResults() {
  return jsonFetch('/results')
}

export function getRuns() {
  return jsonFetch('/runs')
}

export function getRunDetail(runId) {
  return jsonFetch(`/runs/${runId}`)
}

export function getItems() {
  return jsonFetch('/items')
}

export function getSchema() {
  return jsonFetch('/schema')
}

export function validateItems() {
  return jsonFetch('/validate-items')
}

export function getCostSummary() {
  return jsonFetch('/cost-summary')
}

export function runSql(goldSql, modelSql) {
  const params = new URLSearchParams({ gold_sql: goldSql || '', model_sql: modelSql || '' })
  return jsonFetch(`/run-sql?${params}`)
}

export function getPrompt(question) {
  const params = new URLSearchParams({ question: question || '' })
  return jsonFetch(`/prompt?${params}`)
}

export function getSystemPrompt() {
  return jsonFetch('/system-prompt')
}

export function saveSystemPrompt(text) {
  return jsonFetch('/system-prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ system_prompt: text }),
  })
}

export function postChat({ question, provider, model }) {
  return jsonFetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, provider, model }),
  })
}

export function postRunTests({ items, model_key }) {
  return jsonFetch('/run-tests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, model_key }),
  })
}

export const PROVIDERS = {
  ollama: ['mistral:latest'],
  groq: ['llama-3.1-8b-instant', 'openai/gpt-oss-20b', 'openai/gpt-oss-120b'],
}

// Same three roles as src/run.py's MODEL_CONFIG — kept in sync manually
// since the frontend can't import the Python file directly. If you change
// MODEL_CONFIG in src/run.py, update the labels here too.
export const MODEL_ROLES = [
  { key: 'top', label: 'Top API — openai/gpt-oss-120b' },
  { key: 'cheap', label: 'Cheap API — openai/gpt-oss-20b' },
  { key: 'open', label: 'Self-hosted — mistral:latest' },
]