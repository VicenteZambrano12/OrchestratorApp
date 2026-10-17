import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Activity, Code2, Database, GitBranch, Maximize2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { buildWorkflowGraph, fitWorkflowGraph, graphNodeId, playbackEvents } from './workflowGraph'
import './WorkflowMonitor.css'

export function WorkflowDiagram({ trace }) {
  const { t } = useTranslation()
  const events = useMemo(() => playbackEvents(trace.steps, trace.status), [trace.steps, trace.status])
  const [revealed, setRevealed] = useState(trace.status === 'idle' ? 0 : 1)
  const [finished, setFinished] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const viewportRef = useRef(null)
  const terminal = trace.status === 'complete' || trace.status === 'failed'
  const hasNext = revealed < events.length

  useEffect(() => {
    if (hasNext) {
      const timer = setTimeout(() => setRevealed((count) => count + 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [revealed, hasNext])

  useEffect(() => {
    if (!hasNext && terminal && !finished) {
      const timer = setTimeout(() => setFinished(true), 1000)
      return () => clearTimeout(timer)
    }
  }, [hasNext, terminal, finished])

  useEffect(() => {
    const viewport = viewportRef.current
    const observer = new viewport.ownerDocument.defaultView.ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [])

  const visibleEvents = events.slice(0, revealed)
  const status = trace.status === 'idle' ? 'idle' : finished ? trace.status : 'running'
  const graph = buildWorkflowGraph(visibleEvents, status)
  const { nodes, width, height } = graph
  const selected = nodes.find(({ id }) => id === selectedId)
  const activeEvent = visibleEvents.at(-1)
  const activeNode = nodes.find(({ id }) => id === graphNodeId(activeEvent ?? { id: '' }))
  const inspected = selected ?? activeNode
  const scale = fitWorkflowGraph(size, graph)
  const statusLabel = status === 'running' && terminal ? 'Playing execution' :
    { idle: 'Waiting for a request', running: 'Live', complete: 'Complete', failed: 'Interrupted' }[status]

  return <main className="workflow-monitor">
    <header className="workflow-heading">
      <div><span className="workflow-eyebrow"><GitBranch size={16} />{t('SYSTEM MAP')}</span><h1>{t('Live request flow')}</h1></div>
      <span className={`workflow-status ${status}`} role="status"><span />{t(statusLabel)}</span>
    </header>
    <p className="workflow-description">{t('Full tree always visible. Highlights advance one node per second without delaying the API.')}</p>
    <div className="workflow-workspace">
      <section className="workflow-tree-panel">
        <div className="workflow-toolbar">
          <div className="workflow-legend"><span className="visited" />{t('Executed path')}<span className="unvisited" />{t('Not visited')}</div>
          <span>{revealed} / {events.length} · {t('1 second per node')}</span>
        </div>
        <section ref={viewportRef} className="workflow-viewport" aria-label={t('Request node diagram')}>
          <div className="workflow-canvas" style={{ width, height, transform: `translate(-50%, -50%) scale(${scale})` }}>
            <svg width={width} height={height} aria-hidden="true">
              {nodes.filter(({ parent }) => parent).map((node) => {
                const parent = nodes.find(({ id }) => id === node.parent)
                const x1 = parent.x + 140
                const y1 = parent.y + 76
                const x2 = node.x + 140
                const y2 = node.y
                const side = parent.x + 302
                const path = parent.x === node.x && y2 - y1 > 50
                  ? `M ${parent.x + 280} ${parent.y + 38} H ${side} V ${node.y + 38} H ${node.x + 280}`
                  : `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`
                return <path key={node.id} className={`workflow-edge ${node.state}`} d={path} />
              })}
            </svg>
            {nodes.map((node) => {
              const Icon = node.kind === 'sql' ? Code2 : node.kind === 'source' ? Database : node.id === 'orchestrator' ? GitBranch : Activity
              return <button key={node.id} data-node-id={node.id} className={`workflow-node ${node.state}${selectedId === node.id ? ' selected' : ''}`}
                style={{ left: node.x, top: node.y }} onClick={() => setSelectedId(node.id)} aria-pressed={selectedId === node.id}>
                <Icon size={24} /><span><strong>{t(node.label)}</strong><small>{node.kind === 'sql' && node.source ? node.source :
                  t({ idle: 'Not visited', done: 'Complete', active: 'In progress', failed: 'Interrupted' }[node.state])}</small></span>
              </button>
            })}
          </div>
        </section>
      </section>
      <aside className="workflow-results" aria-label={t('API responses')}>
        <header><h2>{t('API responses')}</h2><small>{t('Live data · visual playback: 1s / node')}</small></header>
        {trace.query && <section><h3>{t('User request')}</h3><p className="workflow-request">{trace.query}</p></section>}
        <section className="workflow-inspector" aria-label={t('Node details')}>
          <div className="workflow-inspector-heading"><h3>{t(inspected?.label ?? 'Waiting for a request')}</h3>
            {selected && <button className="icon-button" aria-label={t('Close node details')} onClick={() => setSelectedId(null)}><X size={16} /></button>}
          </div>
          {inspected?.sql ? <><p><Database size={16} />{inspected.source}</p><pre>{inspected.sql}</pre><small>{t('Bound values and database rows are not displayed.')}</small></> :
            <p>{t('Live execution stages, not private model reasoning. Select a node for details.')}</p>}
        </section>
        {trace.error && <section className="workflow-error" role="alert">{trace.error}</section>}
        <section className="workflow-api-response">
          <h3>{t('Chat API response')}</h3>
          {trace.responses?.length ? trace.responses.map(({ endpoint, data }, index) => <div key={index}>
            <small>{endpoint}</small><pre>{JSON.stringify(data, null, 2)}</pre>
          </div>) : trace.response !== undefined ? <pre>{JSON.stringify(trace.response, null, 2)}</pre> : <p>{t('Waiting for the API response')}</p>}
        </section>
        <section className="workflow-event-log">
          <h3>{t('Execution events')}</h3>
          {visibleEvents.map((event, index) => <details key={`${event.id}_${index}`} open={index === visibleEvents.length - 1}>
            <summary><span>{index + 1}</span>{t(event.kind === 'sql' ? 'SQL query' : event.label)}</summary>
            <pre>{JSON.stringify(event, null, 2)}</pre>
          </details>)}
        </section>
        {finished && !trace.steps.length && <p role="status">{t('This server returned no execution events.')}</p>}
      </aside>
    </div>
  </main>
}

export default function WorkflowMonitor({ trace }) {
  const { t, i18n } = useTranslation()
  const [popup, setPopup] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!popup) return
    const child = popup.window
    const syncAppearance = () => {
      child.document.documentElement.setAttribute('class', document.documentElement.className)
    }
    syncAppearance()
    const observer = new MutationObserver(syncAppearance)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    const onClose = () => setPopup(null)
    const onParentClose = () => child.close()
    child.addEventListener('beforeunload', onClose)
    window.addEventListener('pagehide', onParentClose)
    return () => {
      observer.disconnect()
      child.removeEventListener('beforeunload', onClose)
      window.removeEventListener('pagehide', onParentClose)
      child.close()
    }
  }, [popup])

  useEffect(() => {
    if (!popup) return
    popup.window.document.documentElement.setAttribute('lang', i18n.resolvedLanguage)
    popup.window.document.querySelector('title').replaceChildren(t('Live request flow'))
  }, [popup, i18n.resolvedLanguage, t])

  function openMonitor() {
    if (popup && !popup.window.closed) {
      popup.window.focus()
      return
    }
    const child = window.open('', '', 'popup=yes,width=1440,height=960,resizable=yes,scrollbars=yes')
    if (!child) {
      setError(t('The live map window was blocked. Allow pop-ups for this site and try again.'))
      return
    }
    child.document.title = t('Live request flow')
    child.document.body.classList.add('workflow-window')
    document.querySelectorAll('style, link[rel="stylesheet"]').forEach((style) => {
      child.document.head.appendChild(style.cloneNode(true))
    })
    const container = child.document.createElement('div')
    child.document.body.appendChild(container)
    setError('')
    setPopup({ window: child, container })
  }

  return <>
    <button type="button" className="workflow-launch" onClick={openMonitor} aria-label={t('Open live system map in a new window')}><GitBranch size={17} /><span>{t('Live system map')}</span><Maximize2 size={14} /></button>
    {error && <p className="workflow-popup-error" role="alert">{error}</p>}
    {popup && createPortal(<WorkflowDiagram key={trace.id ?? trace.query ?? 'idle'} trace={trace} />, popup.container)}
  </>
}
