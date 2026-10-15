import ReactMarkdown from 'react-markdown'
import ExplainerCard from '../../../components/ExplainerCard/ExplainerCard'
import SavedRoutine from '../../../components/SavedRoutine/SavedRoutine'

function MarkdownResponse({ content }) {
  return <div className="markdown-response"><ReactMarkdown>{content}</ReactMarkdown></div>
}

function ExplainerResponse({ content }) {
  return Array.isArray(content) ? <ExplainerCard exercises={content} /> : <MarkdownResponse content={content} />
}

const subsystemRenderers = {
  routine_maker: MarkdownResponse,
  exercise_explainer: ExplainerResponse,
  past_routines_analyzer: MarkdownResponse,
  no_system: MarkdownResponse,
}

export function SubsystemResponse({ subsystem, content, savedRoutine }) {
  if (subsystem === 'routine_maker' && savedRoutine) {
    return <SavedRoutine routine={savedRoutine} message={content} />
  }
  const Renderer = subsystemRenderers[subsystem] || MarkdownResponse
  return <Renderer content={content} />
}
