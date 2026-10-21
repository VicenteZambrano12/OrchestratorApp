/**
 * @file Presentation router for normalized agent specialist responses.
 * Structured history, saved routines, and draft plans take priority over Markdown.
 * Transport decoding/validation happens in the API layer; generic text remains
 * renderable when a specialist does not supply a structured response.
 */
import ReactMarkdown from 'react-markdown'
import ExplainerCard from '../../../components/ExplainerCard/ExplainerCard'
import SavedRoutine from '../../../components/SavedRoutine/SavedRoutine'
import RoutineMaker from '../../../components/RoutineMaker/RoutineMaker'
import PastRoutinesReport from '../../../components/PastRoutinesReport/PastRoutinesReport'

/**
 * Renders plain agent Markdown through the shared response styling.
 * @param {object} props - Text response properties.
 * @param {string} props.content - Agent-generated Markdown.
 * @returns {import('react').ReactElement} Markdown response body.
 */
function MarkdownResponse({ content }) {
  return <div className="markdown-response"><ReactMarkdown>{content}</ReactMarkdown></div>
}

/**
 * Chooses validated exercise cards or the explainer's compatible text response.
 * @param {object} props - Explainer properties.
 * @param {string|import('../../ExplainerCard/exercise-data/exerciseData').Exercise[]} props.content - Normalized specialist content.
 * @returns {import('react').ReactElement} Exercise card or Markdown body.
 */
function ExplainerResponse({ content }) {
  return Array.isArray(content) ? <ExplainerCard exercises={content} /> : <MarkdownResponse content={content} />
}

const subsystemRenderers = {
  routine_maker: MarkdownResponse,
  exercise_explainer: ExplainerResponse,
  past_routines_analyzer: MarkdownResponse,
  no_system: MarkdownResponse,
}

/**
 * Selects the response component without owning request/loading/error state.
 * @param {object} props - Normalized response properties.
 * @param {string} [props.subsystem] - Specialist identifier; user text may omit it.
 * @param {string|import('../../ExplainerCard/exercise-data/exerciseData').Exercise[]} props.content - Normalized Markdown/cards.
 * @param {{id?: number, name: string}|null} [props.savedRoutine] - Confirmed persistence descriptor.
 * @param {import('../../RoutineMaker/routine-data/routineData').RoutinePlan|null} [props.routine] - Complete structured draft.
 * @param {import('../../PastRoutinesReport/report-data/reportData').PastRoutinesAnalysis} [props.analysis] - Validated history envelope.
 * @param {(name: string) => void} [props.onExplainExercise] - Follow-up prompt action passed to plan rows.
 * @returns {import('react').ReactElement} Highest-priority structured view or Markdown fallback.
 */
export function SubsystemResponse({ subsystem, content, savedRoutine, routine, analysis, onExplainExercise }) {
  if (subsystem === 'past_routines_analyzer' && analysis) {
    return <PastRoutinesReport analysis={analysis} />
  }
  if (subsystem === 'routine_maker' && savedRoutine) {
    return <SavedRoutine routine={savedRoutine} message={content} />
  }
  if (subsystem === 'routine_maker' && routine) {
    return <>{content && <MarkdownResponse content={content} />}<RoutineMaker key={JSON.stringify(routine)} routine={routine} onExplainExercise={onExplainExercise} /></>
  }
  const Renderer = subsystemRenderers[subsystem] || MarkdownResponse
  return <Renderer content={content} />
}
