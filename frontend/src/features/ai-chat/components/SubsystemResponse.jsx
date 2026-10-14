import ReactMarkdown from 'react-markdown'

function MarkdownResponse({ content }) {
  return <div className="markdown-response"><ReactMarkdown>{content}</ReactMarkdown></div>
}

// Future specialist templates plug into this registry without changing the chat.
const subsystemRenderers = {
  routine_maker: MarkdownResponse,
  exercise_explainer: MarkdownResponse,
  past_routines_analyzer: MarkdownResponse,
  no_system: MarkdownResponse,
}

export function SubsystemResponse({ subsystem, content }) {
  const Renderer = subsystemRenderers[subsystem] || MarkdownResponse
  return <Renderer content={content} />
}
