import { useState, useEffect, useMemo, useCallback, Fragment } from 'react'
import { getResults, getItems, getRuns, getRunDetail, validateItems, postRunTests, runSql, getPrompt, getSystemPrompt, saveSystemPrompt, MODEL_ROLES } from '../api'
import { Loading, ErrorBox, Badge, Stat, Collapsible, CodeBlock, EmptyState, Spinner, SuccessBox } from './ui'

function ResultTable({ label, result }) {
  if (!result) return null
  return (
    <div>
      <div className="code-block-label">{label}</div>
      {result.error ? (
        <div className="muted text-sm" style={{ padding: '0.5rem 0' }}>⚠ {result.error}</div>
      ) : result.rows.length === 0 ? (
        <div className="muted text-sm" style={{ padding: '0.5rem 0' }}>No rows returned</div>
      ) : (
        <div style={{ overflowX: 'auto', maxHeight: 220, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
          <table style={{ margin: 0 }}>
            <thead>
              <tr>
                {result.columns.map((col) => <th key={col}>{col}</th>)}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((r, i) => (
                <tr key={i}>
                  {result.columns.map((col) => (
                    <td key={col} className="text-sm">{r[col] ?? '—'}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="muted text-sm" style={{ marginTop: 4 }}>{result.rows.length} row{result.rows.length !== 1 ? 's' : ''}</div>
    </div>
  )
}

export default function TestLab() {
  const [resultsData, setResultsData] = useState(null)
  const [itemsData, setItemsData] = useState(null)
  const [runsData, setRunsData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  // Active rows state: either CSV results or a loaded run
  const [activeRows, setActiveRows] = useState(null)
  const [activeSource, setActiveSource] = useState('csv')

  // Run history selection
  const [selectedRunId, setSelectedRunId] = useState('')
  const [runLoading, setRunLoading] = useState(false)
  const [runError, setRunError] = useState(null)

  // Validation
  const [validating, setValidating] = useState(false)
  const [validationResult, setValidationResult] = useState(null)
  const [validationError, setValidationError] = useState(null)

  // File upload
  const [uploadedItems, setUploadedItems] = useState(null)
  const [uploadIsCustom, setUploadIsCustom] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [uploadModelKey, setUploadModelKey] = useState('open')
  const [runTestsLoading, setRunTestsLoading] = useState(false)
  const [runTestsError, setRunTestsError] = useState(null)
  const [runTestsResult, setRunTestsResult] = useState(null)

  // System prompt editor
  const [sysPrompt, setSysPrompt] = useState('')
  const [sysPromptSaving, setSysPromptSaving] = useState(false)
  const [sysPromptSaved, setSysPromptSaved] = useState(false)
  const [sysPromptError, setSysPromptError] = useState(null)

  // Expanded row SQL results
  const [rowResults, setRowResults] = useState({}) // idx -> { loading, data, error }

  // Filters
  const [search, setSearch] = useState('')
  const [filterModel, setFilterModel] = useState('')
  const [filterOutcome, setFilterOutcome] = useState('')
  const [expandedRow, setExpandedRow] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [results, items, runs, sp] = await Promise.all([getResults(), getItems(), getRuns(), getSystemPrompt()])
        if (cancelled) return
        setResultsData(results)
        setItemsData(items)
        setRunsData(runs)
        setSysPrompt(sp.system_prompt || '')
        setActiveRows(results.rows || [])
        setActiveSource('csv')
        // Default the run-tests panel to the full benchmark set so the
        // provider/model picker and "Start test run" button are usable
        // right away, without requiring a file upload first.
        setUploadedItems(items.items || [])
      } catch (err) {
        if (!cancelled) setLoadError(err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const modelKeys = useMemo(() => {
    if (!activeRows) return []
    return [...new Set(activeRows.map((r) => r.model_key))].sort()
  }, [activeRows])

  const stats = useMemo(() => {
    if (!activeRows || activeRows.length === 0)
      return { total: 0, accuracy: 0, p95: 0 }
    const total = activeRows.length
    const correct = activeRows.filter((r) => r.correct).length
    const accuracy = total > 0 ? (correct / total) * 100 : 0
    const latencies = activeRows.map((r) => r.latency_ms || 0).sort((a, b) => a - b)
    const p95Index = Math.ceil(latencies.length * 0.95) - 1
    const p95 = latencies[Math.max(0, p95Index)] || 0
    return { total, correct, accuracy, p95 }
  }, [activeRows])

  const filteredRows = useMemo(() => {
    if (!activeRows) return []
    return activeRows.filter((r) => {
      if (search) {
        const q = search.toLowerCase()
        if (
          !r.question?.toLowerCase().includes(q) &&
          !r.item_id?.toString().includes(q) &&
          !r.reason?.toLowerCase().includes(q)
        )
          return false
      }
      if (filterModel && r.model_key !== filterModel) return false
      if (filterOutcome === 'correct' && !r.correct) return false
      if (filterOutcome === 'failed' && r.correct) return false
      return true
    })
  }, [activeRows, search, filterModel, filterOutcome])

  const handleRunSelect = useCallback(async (runId) => {
    setSelectedRunId(runId)
    if (!runId) {
      setActiveRows(resultsData?.rows || [])
      setActiveSource('csv')
      setRunError(null)
      return
    }
    setRunLoading(true)
    setRunError(null)
    try {
      const detail = await getRunDetail(runId)
      setActiveRows(detail.rows || [])
      setActiveSource(`run:${runId}`)
    } catch (err) {
      setRunError(err)
    } finally {
      setRunLoading(false)
    }
  }, [resultsData])

  const handleValidate = async () => {
    setValidating(true)
    setValidationError(null)
    setValidationResult(null)
    try {
      const result = await validateItems()
      setValidationResult(result)
    } catch (err) {
      setValidationError(err)
    } finally {
      setValidating(false)
    }
  }

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadError(null)
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const text = ev.target.result
        const lines = text.trim().split('\n').filter(Boolean)
        const parsed = lines.map((line, i) => {
          try {
            return JSON.parse(line)
          } catch {
            throw new Error(`Line ${i + 1} is not valid JSON`)
          }
        })
        if (parsed.length === 0) throw new Error('File contains no items')
        if (parsed.length > 100) throw new Error(`File has ${parsed.length} items, max is 100`)
        setUploadedItems(parsed)
        setUploadIsCustom(true)
      } catch (err) {
        // Keep whatever set was already loaded (default or previous custom
        // upload) so the run controls stay usable after a bad file.
        setUploadError(err.message)
      }
    }
    reader.onerror = () => setUploadError('Failed to read file')
    reader.readAsText(file)
  }

  const handleStartRun = async () => {
    if (!uploadedItems) return
    setRunTestsLoading(true)
    setRunTestsError(null)
    setRunTestsResult(null)
    try {
      const result = await postRunTests({ items: uploadedItems, model_key: uploadModelKey })
      setRunTestsResult(result)
      // Refresh runs list
      const runs = await getRuns()
      setRunsData(runs)
    } catch (err) {
      setRunTestsError(err)
    } finally {
      setRunTestsLoading(false)
    }
  }

  const handleSaveSysPrompt = async () => {
    setSysPromptSaving(true)
    setSysPromptError(null)
    setSysPromptSaved(false)
    try {
      await saveSystemPrompt(sysPrompt)
      setSysPromptSaved(true)
      setTimeout(() => setSysPromptSaved(false), 3000)
    } catch (err) {
      setSysPromptError(err)
    } finally {
      setSysPromptSaving(false)
    }
  }

  const handleRowExpand = async (idx, row) => {
    if (expandedRow === idx) {
      setExpandedRow(null)
      return
    }
    setExpandedRow(idx)
    if (rowResults[idx]) return
    setRowResults((prev) => ({ ...prev, [idx]: { loading: true } }))
    try {
      const [sqlData, promptData] = await Promise.all([
        runSql(row.gold_sql, row.raw_output),
        getPrompt(row.question),
      ])
      setRowResults((prev) => ({ ...prev, [idx]: { loading: false, data: sqlData, prompt: promptData } }))
    } catch (err) {
      setRowResults((prev) => ({ ...prev, [idx]: { loading: false, error: err.message } }))
    }
  }

  if (loading) return <Loading label="Loading test data…" />
  if (loadError) return <ErrorBox error={loadError} />

  return (
    <div>
      {/* Overview stats */}
      <div className="stats-grid">
        <Stat label="Evaluations" value={stats.total} />
        <Stat label="Accuracy" value={`${stats.accuracy.toFixed(1)}%`} sub={`${stats.correct ?? 0} correct`} />
        <Stat label="P95 latency" value={`${stats.p95} ms`} />
        <Stat label="Benchmark items" value={itemsData?.items?.length ?? 53} sub={itemsData?.name} />
        <Stat label="Past runs" value={runsData?.runs?.length ?? 0} />
      </div>

      {/* System prompt editor */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="card-title">System prompt</div>
          <div className="flex items-center gap-sm">
            {sysPromptSaved && <Badge variant="success">Saved</Badge>}
            <button className="btn btn-primary" onClick={handleSaveSysPrompt} disabled={sysPromptSaving}>
              {sysPromptSaving ? <><Spinner /> Saving…</> : 'Save'}
            </button>
          </div>
        </div>
        <div className="text-sm muted" style={{ marginBottom: '0.5rem' }}>
          Changes apply immediately to all subsequent model calls — no restart needed.
        </div>
        <textarea
          value={sysPrompt}
          onChange={(e) => setSysPrompt(e.target.value)}
          rows={6}
          style={{ width: '100%', fontFamily: 'var(--font-mono, monospace)', fontSize: '0.85rem', resize: 'vertical', boxSizing: 'border-box' }}
        />
        {sysPromptError && <div className="mt-sm"><ErrorBox error={sysPromptError} /></div>}
      </div>

      {/* Run a new test */}
      <div className="card">
        <div className="card-title">Run a new test batch</div>
        <div className="form-row">
          <label className="upload-zone" style={{ flex: 1 }}>
            <input type="file" accept=".jsonl,.txt" className="file-input" onChange={handleFileUpload} />
            {uploadedItems && uploadedItems.length > 0 ? (
              <div>
                <div style={{ fontWeight: 600, color: 'var(--success)', marginBottom: 4 }}>
                  ✓ {uploadedItems.length} items {uploadIsCustom ? 'loaded' : 'ready (full benchmark set)'}
                </div>
                <div className="text-sm muted">Click to upload a JSONL file and test a custom subset instead</div>
              </div>
            ) : (
              <div>
                <div className="text-sm" style={{ marginBottom: 4 }}>Upload a JSONL file</div>
                <div className="text-sm muted">One JSON object per line (max 100 items)</div>
              </div>
            )}
          </label>
        </div>
        {uploadError && <ErrorBox error={uploadError} />}
        {uploadedItems && uploadedItems.length > 0 && (
          <div className="mt-sm">
            <div className="form-row" style={{ alignItems: 'flex-end' }}>
              <div className="form-group" style={{ maxWidth: 280 }}>
                <label className="form-label">Model (same 3 roles as src/run.py)</label>
                <select value={uploadModelKey} onChange={(e) => setUploadModelKey(e.target.value)}>
                  {MODEL_ROLES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                </select>
              </div>
              <button className="btn btn-primary" onClick={handleStartRun} disabled={runTestsLoading}>
                {runTestsLoading ? <><Spinner /> Running…</> : 'Start test run'}
              </button>
            </div>
          </div>
        )}
        {runTestsError && <div className="mt-sm"><ErrorBox error={runTestsError} /></div>}
        {runTestsResult && (
          <div className="mt-sm">
            <SuccessBox>
              Run completed ({runTestsResult.model_key}: {runTestsResult.model}) — {runTestsResult.rows?.filter((r) => r.correct).length ?? 0} / {runTestsResult.total} correct.
              Appended to results/per_item.csv — check the Cost & benchmarks tab.
            </SuccessBox>
            <div className="text-sm muted mt-sm">
              Running the same role again adds more rows for the same items (same as running src/run.py twice) —
              delete results/per_item.csv first if you want to start that model over from zero.
            </div>
          </div>
        )}
      </div>

      {/* Verify gold queries */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="section-title">Verify gold queries</div>
          <button className="btn btn-secondary" onClick={handleValidate} disabled={validating}>
            {validating ? <><Spinner /> Verifying…</> : 'Verify gold queries'}
          </button>
        </div>
        {validationError && <div className="mt-sm"><ErrorBox error={validationError} /></div>}
        {validationResult && (
          <div className="mt-sm">
            {validationResult.ok ? (
              <div className="flex items-center gap-sm"><Badge variant="success">All {validationResult.total} gold queries pass</Badge></div>
            ) : (
              <div>
                <div className="flex items-center gap-sm mb-sm">
                  <Badge variant="error">{validationResult.errors?.length ?? 0} errors</Badge>
                  <Badge variant="warning">{validationResult.mismatches?.length ?? 0} mismatches</Badge>
                </div>
                {validationResult.errors?.length > 0 && (
                  <div className="mb-sm">
                    <div className="code-block-label">Errors</div>
                    {validationResult.errors.map((e, i) => (
                      <div key={i} className="text-sm mb-sm">
                        <strong>Item {e.id}:</strong> <span className="muted">{e.error}</span>
                      </div>
                    ))}
                  </div>
                )}
                {validationResult.mismatches?.length > 0 && (
                  <div>
                    <div className="code-block-label">Row count mismatches</div>
                    {validationResult.mismatches.map((m, i) => (
                      <div key={i} className="text-sm mb-sm">
                        <strong>Item {m.id}:</strong> <span className="muted">expected {m.expected} rows, got {m.actual}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Run history */}
      <div className="card">
        <div className="section-header">
          <div className="section-title">Run history</div>
          <div className="flex items-center gap-sm">
            <select value={selectedRunId} onChange={(e) => handleRunSelect(e.target.value)} style={{ width: 'auto', minWidth: 280 }}>
              <option value="">Saved CSV results (all)</option>
              {runsData?.runs?.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {new Date(run.started_at).toLocaleString()} — {run.model} ({(run.accuracy * 100).toFixed(0)}%)
                </option>
              ))}
            </select>
          </div>
        </div>
        {runLoading && <Loading label="Loading run…" />}
        {runError && <ErrorBox error={runError} />}
        {!runLoading && !runError && runsData?.runs?.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Items</th>
                  <th>Correct</th>
                  <th>Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {runsData.runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className={`row-expandable ${selectedRunId === run.run_id ? 'row-expanded' : ''}`}
                    onClick={() => handleRunSelect(selectedRunId === run.run_id ? '' : run.run_id)}
                  >
                    <td>{new Date(run.started_at).toLocaleString()}</td>
                    <td className="text-mono">{run.provider}</td>
                    <td className="text-mono">{run.model}</td>
                    <td>{run.item_count}</td>
                    <td>{run.correct}</td>
                    <td>{(run.accuracy * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!runLoading && !runError && (!runsData?.runs || runsData.runs.length === 0) && (
          <EmptyState icon="–" title="No past runs yet" desc="Start a test batch above to see run history here." />
        )}
      </div>

      {/* Results table */}
      <div className="card">
        <div className="section-header">
          <div className="section-title">
            Results {activeSource !== 'csv' && <Badge variant="neutral">{activeSource}</Badge>}
          </div>
        </div>

        <div className="filters-bar">
          <input
            type="text"
            className="search-input"
            placeholder="Search by question, ID, or reason…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select value={filterModel} onChange={(e) => setFilterModel(e.target.value)}>
            <option value="">All models</option>
            {modelKeys.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <select value={filterOutcome} onChange={(e) => setFilterOutcome(e.target.value)}>
            <option value="">All outcomes</option>
            <option value="correct">Correct</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        {filteredRows.length === 0 ? (
          <EmptyState icon="–" title="No results found" desc="Adjust your search or filters, or run a test batch to see results." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Model</th>
                  <th>Question</th>
                  <th>Result</th>
                  <th>Reason</th>
                  <th>Latency</th>
                  <th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, i) => {
                  const idx = `${row.item_id}-${i}`
                  const isExpanded = expandedRow === idx
                  const rr = rowResults[idx]
                  return (
                    <Fragment key={idx}>
                      <tr
                        className={`row-expandable ${isExpanded ? 'row-expanded' : ''}`}
                        onClick={() => handleRowExpand(idx, row)}
                      >
                        <td>{row.item_id}</td>
                        <td className="text-mono">{row.model_key}</td>
                        <td style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.question}</td>
                        <td><Badge variant={row.correct ? 'success' : 'error'}>{row.correct ? 'correct' : 'failed'}</Badge></td>
                        <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} className="muted">{row.reason || '—'}</td>
                        <td>{row.latency_ms}ms</td>
                        <td className="text-mono text-sm">{row.input_tokens ?? '—'}/{row.output_tokens ?? '—'}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="row-detail">
                          <td colSpan={7}>
                            {/* Prompt given to the LLM */}
                            {rr?.loading && <Loading label="Loading…" />}
                            {rr?.prompt && (
                              <div style={{ marginBottom: '1rem' }}>
                                <div className="code-block-label">Prompt given to the LLM</div>
                                <CodeBlock>{rr.prompt.user_prompt}</CodeBlock>
                              </div>
                            )}
                            {/* SQL queries */}
                            <div className="grid-2" style={{ marginBottom: '1rem' }}>
                              <div>
                                <div className="code-block-label">Gold SQL</div>
                                <CodeBlock>{row.gold_sql || '—'}</CodeBlock>
                              </div>
                              <div>
                                <div className="code-block-label">Model output</div>
                                <CodeBlock>{row.raw_output || '—'}</CodeBlock>
                              </div>
                            </div>
                            {/* Query results */}
                            {rr?.loading && <Loading label="Running queries…" />}
                            {rr?.error && <ErrorBox error={rr.error} />}
                            {rr?.data && (
                              <div className="grid-2">
                                <ResultTable label="Expected result" result={rr.data.gold} />
                                <ResultTable label="Model result" result={rr.data.model} />
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}