import { useState } from 'react'

export function Spinner() {
  return <span className="spinner" />
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading">
      <Spinner />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBox({ error }) {
  if (!error) return null
  return (
    <div className="error-box">
      {typeof error === 'string' ? error : error.message}
      {error.payload && (error.payload.sql || error.payload.raw_output) && (
        <pre>{error.payload.sql || error.payload.raw_output}</pre>
      )}
    </div>
  )
}

export function SuccessBox({ children }) {
  return <div className="success-box">{children}</div>
}

export function EmptyState({ title, desc, icon = '○' }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {desc && <div className="empty-state-desc">{desc}</div>}
    </div>
  )
}

export function Badge({ variant = 'neutral', children }) {
  return <span className={`badge badge-${variant}`}>{children}</span>
}

export function Collapsible({ trigger, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <div className="collapsible-trigger" onClick={() => setOpen(!open)}>
        <span className={`collapsible-chevron ${open ? 'open' : ''}`}>▶</span>
        {trigger}
      </div>
      {open && <div className="mt-sm">{children}</div>}
    </div>
  )
}

export function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export function CodeBlock({ label, children }) {
  return (
    <div>
      {label && <div className="code-block-label">{label}</div>}
      <pre className="code-block">{children}</pre>
    </div>
  )
}
