import { useState, useEffect, useRef } from 'react'
import './DemoServiceLogs.css'

export default function DemoServiceLogs() {
  const [inputPort, setInputPort] = useState('')
  const [activePort, setActivePort] = useState(null)
  const [logs, setLogs] = useState([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const [injecting, setInjecting] = useState(false)
  const [injectCount, setInjectCount] = useState(0)
  const [incidentStatus, setIncidentStatus] = useState(null) // 'triggered' | 'error' | null

  const logBodyRef = useRef(null)
  const esRef = useRef(null)
  const autoScrollRef = useRef(true)
  const injectAbortRef = useRef(null)

  function startWatching(port) {
    const p = parseInt(port, 10)
    if (!p || p < 1 || p > 65535) return
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    setLogs([])
    setError(null)
    setConnected(false)
    setActivePort(p)

    const es = new EventSource(`/demo-services/logs/${p}`)
    esRef.current = es
    es.onopen = () => { setConnected(true); setError(null); }
    es.onmessage = (e) => {
      try {
        const { line } = JSON.parse(e.data)
        setLogs(prev => {
          const next = [...prev, line]
          return next.length > 2000 ? next.slice(-2000) : next
        })
      } catch {}
    }
    es.onerror = () => {
      setConnected(false)
      setError('Backend connection lost — check that the backend is running.')
    }
  }

  function stopWatching() {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    stopInject()
    setConnected(false)
    setActivePort(null)
  }

  function clearLogs() { setLogs([]) }

  async function startInject() {
    if (!activePort || injecting) return
    const abort = new AbortController()
    injectAbortRef.current = abort
    setInjecting(true)
    setInjectCount(0)
    setIncidentStatus(null)

    // Trigger a service-specific incident — await it and show feedback
    try {
      const resp = await fetch(`/demo-services/${activePort}/trigger-incident`, { method: 'POST' })
      if (resp.ok) {
        setIncidentStatus('triggered')
        setTimeout(() => setIncidentStatus(null), 4000)
      } else {
        setIncidentStatus('error')
        setTimeout(() => setIncidentStatus(null), 4000)
      }
    } catch {
      setIncidentStatus('error')
      setTimeout(() => setIncidentStatus(null), 4000)
    }

    let i = 0
    while (!abort.signal.aborted) {
      try {
        const res = await fetch(`/demo-services/${activePort}/payment`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ userId: `user_${i % 100}`, amount: Math.round(Math.random() * 500) + 1 }),
          signal: abort.signal,
        })
        if (res.ok) { i++; setInjectCount(i) }
      } catch { break }
      await new Promise(r => setTimeout(r, 100))
    }
    setInjecting(false)
  }

  function stopInject() {
    if (injectAbortRef.current) { injectAbortRef.current.abort(); injectAbortRef.current = null }
    setInjecting(false)
  }

  useEffect(() => {
    if (autoScrollRef.current && logBodyRef.current) {
      logBodyRef.current.scrollTop = logBodyRef.current.scrollHeight
    }
  }, [logs])

  function handleScroll() {
    const el = logBodyRef.current
    if (!el) return
    autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }

  useEffect(() => () => {
    if (esRef.current) esRef.current.close()
    if (injectAbortRef.current) injectAbortRef.current.abort()
  }, [])

  return (
    <div className="dsl-panel">
      <div className="dsl-header">
        <span className="dsl-title">Service Log Watcher</span>
        <div className="dsl-controls">
          <div className="dsl-input-row">
            <input
              type="number"
              className="dsl-port-input"
              placeholder="Enter port…"
              value={inputPort}
              min={1}
              max={65535}
              onChange={e => setInputPort(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && startWatching(inputPort)}
            />
            <button
              className="dsl-btn watch"
              onClick={() => startWatching(inputPort)}
              disabled={!inputPort}
            >
              Watch
            </button>
            {connected && (
              <button className="dsl-btn stop" onClick={stopWatching}>Stop</button>
            )}
            {logs.length > 0 && (
              <button className="dsl-btn clear" onClick={clearLogs}>Clear</button>
            )}
            {connected && !injecting && (
              <button className="dsl-btn inject" onClick={startInject}>
                Inject Load
              </button>
            )}
            {injecting && (
              <button className="dsl-btn inject-stop" onClick={stopInject}>
                Stop ({injectCount} req)
              </button>
            )}
          </div>
        </div>
        {activePort && (
          <div className="dsl-watching">Watching :{activePort}</div>
        )}
        {error && <div className="dsl-error">{error}</div>}
      </div>

      <div className="dsl-body" ref={logBodyRef} onScroll={handleScroll}>
        {logs.length === 0 ? (
          <div className="dsl-empty">
            Enter a port and click <strong>Watch</strong> to stream live logs.
          </div>
        ) : (
          logs.map((line, i) => {
            const isErr = /error|exception|warn|fail/i.test(line)
            const isGood = /started|listening|ready|✓/i.test(line)
            return (
              <div
                key={i}
                className={`dsl-line ${isErr ? 'err' : isGood ? 'ok' : ''}`}
              >
                <span className="dsl-line-num">{i + 1}</span>
                <span className="dsl-line-text">{line}</span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
