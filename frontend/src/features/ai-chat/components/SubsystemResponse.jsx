import ReactMarkdown from 'react-markdown'
import ExplainerCard from '../../../components/ExplainerCard/ExplainerCard'
import SavedRoutine from '../../../components/SavedRoutine/SavedRoutine'
import RoutineMaker from '../../../components/RoutineMaker/RoutineMaker'

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

export function SubsystemResponse({ subsystem, content, savedRoutine, routine, onExplainExercise }) {
  if (subsystem === 'routine_maker' && savedRoutine) {
    return <SavedRoutine routine={savedRoutine} message={content} />
  }
  if (subsystem === 'routine_maker' && routine) {
    return <>{content && <MarkdownResponse content={content} />}<RoutineMaker key={JSON.stringify(routine)} routine={routine} onExplainExercise={onExplainExercise} /></>
  }
  const Renderer = subsystemRenderers[subsystem] || MarkdownResponse
  return <Renderer content={content} />
}
