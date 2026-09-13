import { useState, useRef, useEffect } from 'react'
import { postChat, PROVIDERS } from '../api'
import { Spinner, Badge, Collapsible, CodeBlock, EmptyState } from './ui'

export default function AskSql() {
  const [question, setQuestion] = useState('')
  const [provider, setProvider] = useState('ollama')
  const [model, setModel] = useState(PROVIDERS.ollama[0])
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState([])

  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading])

  function handleProviderChange(p) {
    setProvider(p)
    setModel(PROVIDERS[p][0])
  }

  async function handleSubmit(e) {
    e?.preventDefault()
    const q = question.trim()
    if (!q || loading) return

    const userMsg = { role: 'user', content: q, id: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setQuestion('')
    setLoading(true)

    try {
      const data = await postChat({ question: q, provider, model })
      const aiMsg = { role: 'assistant', content: data, id: Date.now() + 1, error: false }
      setMessages((prev) => [...prev, aiMsg])
    } catch (err) {
      const aiMsg = {
        role: 'assistant',
        content: {
          error: typeof err === 'string' ? err : err.message,
          payload: err.payload,
          provider,
          model,
        },
        id: Date.now() + 1,
        error: true,
      }
      setMessages((prev) => [...prev, aiMsg])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function handleClear() {
    setMessages([])
  }

  const models = PROVIDERS[provider] || []

  return (
    <div className="chat-container">
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && !loading && (
          <div className="chat-empty">
            <div className="chat-empty-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <ellipse cx="12" cy="5" rx="9" ry="3" />
                <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
                <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
              </svg>
            </div>
            <div className="chat-empty-title">Ask a question about your database</div>
            <div className="chat-empty-desc">Type a natural-language question and the model will generate SQL, run it, and show you the results.</div>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chat-suggestion" onClick={() => { setQuestion(s); inputRef.current?.focus() }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) =>
          msg.role === 'user' ? (
            <ChatMessageUser key={msg.id} text={msg.content} />
          ) : (
            <ChatMessageAssistant key={msg.id} message={msg} />
          )
        )}

        {loading && <ChatMessageThinking model={model} />}
      </div>

      <div className="chat-input-area">
        {messages.length > 0 && (
          <button className="chat-clear" onClick={handleClear} title="Clear conversation">
            Clear
          </button>
        )}
        <div className="chat-input-row">
          <div className="chat-input-selects">
            <select value={provider} onChange={(e) => handleProviderChange(e.target.value)} className="chat-select">
              <option value="ollama">ollama</option>
              <option value="groq">groq</option>
            </select>
            <select value={model} onChange={(e) => setModel(e.target.value)} className="chat-select">
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        <form onSubmit={handleSubmit} className="chat-input-form">
          <textarea
            ref={inputRef}
            rows={1}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question…  (Enter to send, Shift+Enter for new line)"
            className="chat-textarea"
            disabled={loading}
          />
          <button type="submit" className="chat-send-btn" disabled={loading || !question.trim()}>
            {loading ? <Spinner /> : <SendIcon />}
          </button>
        </form>
      </div>
    </div>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function UserAvatar() {
  return (
    <div className="chat-avatar chat-avatar-user">You</div>
  )
}

function BotAvatar() {
  return (
    <div className="chat-avatar chat-avatar-bot">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
        <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
      </svg>
    </div>
  )
}

function ChatMessageUser({ text }) {
  return (
    <div className="chat-msg chat-msg-user">
      <div className="chat-msg-content">
        <div className="chat-bubble chat-bubble-user">{text}</div>
      </div>
      <UserAvatar />
    </div>
  )
}

function ChatMessageAssistant({ message }) {
  const { content, error } = message

  if (error) {
    return (
      <div className="chat-msg chat-msg-bot">
        <BotAvatar />
        <div className="chat-msg-content">
          <div className="chat-bubble chat-bubble-error">
            <div className="chat-error-title">Something went wrong</div>
            <div className="chat-error-text">{content.error}</div>
            {content.payload && (content.payload.sql || content.payload.raw_output) && (
              <pre className="chat-error-pre">{content.payload.sql || content.payload.raw_output}</pre>
            )}
          </div>
        </div>
      </div>
    )
  }

  const { sql, raw_output, rows, columns, row_count, truncated, latency_ms, usage, provider, model } = content
  const cols = columns || (rows && rows.length > 0 ? Object.keys(rows[0]) : [])

  return (
    <div className="chat-msg chat-msg-bot">
      <BotAvatar />
      <div className="chat-msg-content">
        <div className="chat-bubble chat-bubble-bot">
          <div className="chat-response-header">
            <Badge variant="neutral">{provider} · {model}</Badge>
            <div className="chat-response-meta">
              <span>{(latency_ms / 1000).toFixed(2)}s</span>
              <span className="chat-meta-dot" />
              <span>{usage?.input_tokens ?? 0} in / {usage?.output_tokens ?? 0} out</span>
              <span className="chat-meta-dot" />
              <span>{row_count} rows{truncated ? ' (truncated)' : ''}</span>
            </div>
          </div>

          <div className="chat-response-section">
            <div className="code-block-label">Generated SQL</div>
            <CodeBlock>{sql}</CodeBlock>
          </div>

          {rows && rows.length > 0 && (
            <div className="chat-response-section">
              <div className="code-block-label">Results {truncated && <Badge variant="warning">showing 50</Badge>}</div>
              <div className="table-wrap chat-table">
                <table>
                  <thead>
                    <tr>
                      {cols.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 50).map((row, i) => (
                      <tr key={i}>
                        {cols.map((col) => (
                          <td key={col}>{formatCell(row[col])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {(!rows || rows.length === 0) && (
            <div className="chat-response-section">
              <div className="chat-no-rows">No rows returned — the query executed but the result set was empty.</div>
            </div>
          )}

          <div className="chat-response-section">
            <Collapsible trigger="Raw model output">
              <CodeBlock>{raw_output}</CodeBlock>
            </Collapsible>
          </div>
        </div>
      </div>
    </div>
  )
}

function ChatMessageThinking({ model }) {
  return (
    <div className="chat-msg chat-msg-bot">
      <BotAvatar />
      <div className="chat-msg-content">
        <div className="chat-bubble chat-bubble-bot chat-thinking">
          <div className="chat-thinking-dots">
            <span /><span /><span />
          </div>
          <span className="chat-thinking-label">Generating SQL with {model}…</span>
        </div>
      </div>
    </div>
  )
}

function formatCell(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

const SUGGESTIONS = [
  'Which 5 customers spent the most?',
  'What are the top 10 most sold tracks?',
  'How many invoices were billed per country?',
  'Which genres generate the most revenue?',
]
