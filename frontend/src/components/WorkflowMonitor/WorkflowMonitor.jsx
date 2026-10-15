import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Activity, Code2, Database, GitBranch, Maximize2, Minus, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { buildWorkflowGraph } from './workflowGraph'
import './WorkflowMonitor.css'

function WorkflowDiagram({ trace }) {
  const { t } = useTranslation()
  const [zoom, setZoom] = useState(0.8)
  const [selectedId, setSelectedId] = useState(null)
  const { nodes, width, height } = buildWorkflowGraph(trace.steps, trace.status)
  const selected = nodes.find(({ id }) => id === selectedId)
  const statusLabel = { idle: 'Waiting for a request', running: 'Live', complete: 'Complete', failed: 'Interrupted' }[trace.status]
  return <main className="workflow-monitor">
    <header className="workflow-heading">
      <div><span className="workflow-eyebrow"><GitBranch size={16} />{t('SYSTEM MAP')}</span><h1>{t('Live request flow')}</h1></div>
      <span className={`workflow-status ${trace.status}`} role="status"><span />{t(statusLabel)}</span>
    </header>
    <p className="workflow-description">{t('Live execution stages, not private model reasoning. Select a node for details.')}</p>
    {trace.query && <blockquote className="workflow-request">{trace.query}</blockquote>}
    <div className="workflow-toolbar">
      <div className="workflow-legend"><span className="visited" />{t('Executed path')}<span className="unvisited" />{t('Not visited')}</div>
      <div><button className="icon-button" aria-label={t('Zoom out')} onClick={() => setZoom((value) => Math.max(0.4, value - 0.1))}><Minus size={16} /></button><output>{Math.round(zoom * 100)}%</output><button className="icon-button" aria-label={t('Zoom in')} onClick={() => setZoom((value) => Math.min(1.5, value + 0.1))}><Plus size={16} /></button><button className="icon-button" aria-label={t('Reset zoom')} onClick={() => setZoom(0.8)}><Maximize2 size={16} /></button></div>
    </div>
    <section className="workflow-viewport" tabIndex={0} aria-label={t('Request node diagram')}>
      <div style={{ width: width * zoom, height: height * zoom }}>
        <div className="workflow-canvas" style={{ width, height, transform: `scale(${zoom})` }}>
          <svg width={width} height={height} aria-hidden="true">
            {nodes.filter(({ parent }) => parent).map((node) => {
              const parent = nodes.find(({ id }) => id === node.parent)
              const x1 = parent.x + 140
              const y1 = parent.y + 96
              const x2 = node.x + 140
              const y2 = node.y
              return <path key={node.id} className={`workflow-edge ${node.state}`} d={`M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`} />
            })}
          </svg>
          {nodes.map((node) => {
            const Icon = node.kind === 'sql' ? Code2 : node.kind === 'source' ? Database : node.id === 'orchestrator' ? GitBranch : Activity
            return <button key={node.id} className={`workflow-node ${node.state}${selectedId === node.id ? ' selected' : ''}`}
              style={{ left: node.x, top: node.y }} onClick={() => setSelectedId(node.id)} aria-pressed={selectedId === node.id}>
              <Icon size={20} /><span><strong>{node.kind === 'sql' ? t('SQL query') : t(node.label)}</strong><small>{node.kind === 'sql' ? node.source : t({ idle: 'Not visited', done: 'Complete', active: 'In progress', failed: 'Interrupted' }[node.state])}</small></span>
              {node.kind === 'sql' && <code>{node.sql.replace(/\s+/g, ' ').trim()}</code>}
            </button>
          })}
        </div>
      </div>
    </section>
    {selected && <section className="workflow-inspector" aria-label={t('Node details')}>
      <button className="icon-button" aria-label={t('Close node details')} onClick={() => setSelectedId(null)}><X size={16} /></button>
      <h2>{t(selected.label)}</h2>
      {selected.sql ? <><p><Database size={16} />{selected.source}</p><pre>{selected.sql}</pre><small>{t('Bound values and database rows are not displayed.')}</small></> : <p>{selected.id === 'request' ? trace.query || t('Waiting for a request') : t('Only stages reported by the server are highlighted.')}</p>}
    </section>}
    {trace.error && <p className="workflow-error" role="alert">{trace.error}</p>}
    {trace.status === 'complete' && !trace.steps.length && <p role="status">{t('This server returned no execution events.')}</p>}
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
    child.addEventListener('beforeunload', onClose)
    return () => {
      observer.disconnect()
      child.removeEventListener('beforeunload', onClose)
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
    const child = window.open('', '', 'popup=yes,width=1180,height=820,resizable=yes,scrollbars=yes')
    if (!child) {
      setError(t('The live map window was blocked. Allow pop-ups for this site and try again.'))
      return
    }
    child.document.title = t('Live request flow')
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
    {popup && createPortal(<WorkflowDiagram trace={trace} />, popup.container)}
  </>
}
