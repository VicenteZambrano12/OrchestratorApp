/**
 * @file Local tabbed exercise details separating agent Markdown, catalog execution
 * steps, and overview text. Missing catalog content uses explicit translated copy.
 */
import { useId, useState } from 'react'
import { Info, ListChecks, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { parseInstructions } from '../../features/ExplainerCard/exercise-data/exerciseData'

/**
 * Shows the selected details panel using local tab state and a stable accessible ID.
 * @param {object} props - Details properties.
 * @param {import('../../features/ExplainerCard/exercise-data/exerciseData').Exercise} props.exercise - Validated exercise.
 * @returns {import('react').ReactElement} Localized controls and the active detail panel.
 */
export default function ExerciseDetails({ exercise }) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('coach')
  const panelId = useId()
  const instructions = parseInstructions(exercise.instructions)
  return <div className="explainer-details">
    <div className="explainer-tabs" role="group" aria-label={t('Exercise details')}>
      <button type="button" aria-pressed={activeTab === 'coach'} aria-controls={panelId} onClick={() => setActiveTab('coach')}>
        <Sparkles size={15} />{t('Coach Insight')}
      </button>
      <button type="button" aria-pressed={activeTab === 'steps'} aria-controls={panelId} onClick={() => setActiveTab('steps')}>
        <ListChecks size={15} />{t('Execution')} ({instructions.length})
      </button>
      <button type="button" aria-pressed={activeTab === 'about'} aria-controls={panelId} onClick={() => setActiveTab('about')}>
        <Info size={15} />{t('Overview')}
      </button>
    </div>
    <div id={panelId}>
      {activeTab === 'coach' && <div className="explainer-insight markdown-response"><ReactMarkdown>{exercise.llm_explanation}</ReactMarkdown></div>}
      {activeTab === 'steps' && (instructions.length
        ? <ol className="explainer-steps">{instructions.map((step, index) => <li key={index}>{step}</li>)}</ol>
        : <p>{t('No instructions available.')}</p>)}
      {activeTab === 'about' && <p className="explainer-description">{exercise.description || t('No description available.')}</p>}
    </div>
  </div>
}
