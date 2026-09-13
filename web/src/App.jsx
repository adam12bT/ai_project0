import { useState } from 'react'
import AskSql from './components/AskSql'
import TestLab from './components/TestLab'
import CostBenchmarks from './components/CostBenchmarks'
import './App.css'

const TABS = [
  { key: 'ask', label: 'Ask SQL' },
  { key: 'lab', label: 'Test lab' },
  { key: 'cost', label: 'Cost & benchmarks' },
]

function DatabaseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
      <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
    </svg>
  )
}

function App() {
  const [tab, setTab] = useState('ask')

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <span className="header-brand-icon">
            <DatabaseIcon />
          </span>
          Queryroom
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? 'active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="main">
        {tab === 'ask' && <AskSql />}
        {tab === 'lab' && <TestLab />}
        {tab === 'cost' && <CostBenchmarks />}
      </main>
    </div>
  )
}

export default App
