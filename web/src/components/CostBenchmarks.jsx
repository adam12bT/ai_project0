import { useState, useEffect, useMemo } from 'react'
import { getCostSummary } from '../api'
import { Loading, ErrorBox, EmptyState, Badge } from './ui'

const ROLE_LABELS = { top: 'Top API', cheap: 'Cheap API', open: 'Self-hosted' }

export default function CostBenchmarks() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getCostSummary()
      .then((d) => { if (!cancelled) setData(d) })
      .catch((err) => { if (!cancelled) setError(err) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const maxCost = useMemo(() => {
    if (!data?.models?.length) return 0
    return Math.max(...data.models.map((m) => m.cost_at_100x_traffic_usd || 0), 1)
  }, [data])

  if (loading) return <Loading label="Loading cost summary…" />
  if (error) return <ErrorBox error={error} />
  if (!data || !data.models || data.models.length === 0)
    return <EmptyState icon="–" title="No cost data yet" desc="Run a test batch first to see cost and accuracy comparisons across models." />

  return (
    <div>
      {/* Model cards */}
      <div className="cost-grid">
        {data.models.map((model) => {
          const untested = !model.n_total && model.model_key !== 'open'
          return (
          <div key={model.model_key} className={`cost-card ${model.model_key}`}>
            <div className={`cost-card-role ${model.model_key}`}>
              {ROLE_LABELS[model.model_key] || model.model_key}
              {untested && <Badge variant="neutral">Not tested yet</Badge>}
            </div>
            <div className="cost-card-name">{model.model_name || model.model_key}</div>

            <div className="cost-card-row">
              <span className="cost-card-row-label">Accuracy</span>
              <span className="cost-card-row-value">
                {model.n_total > 0 ? `${((model.n_correct / model.n_total) * 100).toFixed(1)}%` : '—'}
                <div className="cost-card-row-note">{model.n_total > 0 ? `${model.n_correct}/${model.n_total} correct` : 'Run a test batch to measure this'}</div>
              </span>
            </div>

            <div className="cost-card-row">
              <span className="cost-card-row-label">P50 latency</span>
              <span className="cost-card-row-value">{model.p50_latency_ms != null ? `${model.p50_latency_ms} ms` : '—'}</span>
            </div>

            <div className="cost-card-row">
              <span className="cost-card-row-label">P95 latency</span>
              <span className="cost-card-row-value">{model.p95_latency_ms != null ? `${model.p95_latency_ms} ms` : '—'}</span>
            </div>

            <div className="cost-card-row">
              <span className="cost-card-row-label">Cost / 1k requests</span>
              <span className="cost-card-row-value">
                {untested ? '—' : formatCost(model.cost_per_1k_requests_usd)}
                {!untested && model.cost_per_1k_requests_note && (
                  <div className="cost-card-row-note">{model.cost_per_1k_requests_note}</div>
                )}
                {untested && <div className="cost-card-row-note">No requests logged for this model yet</div>}
              </span>
            </div>

            {!untested && model.estimated_paid_price_per_1k_requests_usd != null && (
              <div className="cost-card-row">
                <span className="cost-card-row-label">If billed at paid-tier rate</span>
                <span className="cost-card-row-value">
                  {formatCost(model.estimated_paid_price_per_1k_requests_usd)}
                  <div className="cost-card-row-note">what this usage would actually cost, not free</div>
                </span>
              </div>
            )}

            <div className="cost-card-row">
              <span className="cost-card-row-label">Cost / 1k at 100x traffic</span>
              <span className="cost-card-row-value">
                {untested ? '—' : formatCost(model.cost_at_100x_traffic_usd)}
                {!untested && model.cost_at_100x_traffic_note && (
                  <div className="cost-card-row-note">{model.cost_at_100x_traffic_note}</div>
                )}
              </span>
            </div>
          </div>
          )
        })}
      </div>

      {/* Break-even */}
      {data.break_even_requests_per_month != null && (
        <div className="break-even-box">
          <div className="break-even-title">Self-hosting break-even point</div>
          <div className="break-even-value">{data.break_even_requests_per_month.toLocaleString()} <span style={{ fontSize: 16, fontWeight: 400, color: 'var(--text-secondary)' }}>requests / month</span></div>
          <div className="break-even-desc">
            Past this monthly request volume, self-hosting the open model on your own hardware is cheaper than the top API model at its paid-tier rate.
          </div>
          {data.hardware && (
            <div className="break-even-caption">
              Hardware assumptions: ${data.hardware.cost_per_hour_usd}/hour, {data.hardware.requests_per_hour} requests/hour
            </div>
          )}
        </div>
      )}

      {/* Comparison chart */}
      <div className="card">
        <div className="card-title">Cost at 100x traffic — comparison</div>
        <div className="bar-chart">
          {data.models.map((model) => {
            const cost = model.cost_at_100x_traffic_usd || 0
            const pct = maxCost > 0 ? Math.max(2, (cost / maxCost) * 100) : 0
            return (
              <div key={model.model_key} className="bar-row">
                <div className="bar-label">{ROLE_LABELS[model.model_key] || model.model_key}</div>
                <div className="bar-track">
                  <div className={`bar-fill ${model.model_key}`} style={{ width: `${pct}%` }}>
                    {formatCost(cost)}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Pricing details */}
      {data.pricing && (
        <div className="card">
          <div className="card-title">API pricing (per million tokens)</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tier</th>
                  <th>Input / Mtok</th>
                  <th>Output / Mtok</th>
                </tr>
              </thead>
              <tbody>
                {data.pricing.top && (
                  <tr>
                    <td><Badge variant="neutral">Top</Badge></td>
                    <td className="text-mono">${data.pricing.top.input_per_mtok}</td>
                    <td className="text-mono">${data.pricing.top.output_per_mtok}</td>
                  </tr>
                )}
                {data.pricing.cheap && (
                  <tr>
                    <td><Badge variant="neutral">Cheap</Badge></td>
                    <td className="text-mono">${data.pricing.cheap.input_per_mtok}</td>
                    <td className="text-mono">${data.pricing.cheap.output_per_mtok}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function formatCost(usd) {
  if (usd == null) return '—'
  if (usd === 0) return '$0'
  if (usd < 0.01) return '<$0.01'
  if (usd < 1) return `$${usd.toFixed(2)}`
  return `$${usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}