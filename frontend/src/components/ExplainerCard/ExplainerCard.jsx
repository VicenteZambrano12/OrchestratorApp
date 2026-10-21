/**
 * @file Structured exercise-explainer card for validated agent responses.
 * Coordinates exercise navigation, catalog media, and instruction/insight panels.
 * Child keys reset gallery, tab, and image-error state when the exercise changes.
 */
import { useState } from 'react'
import { ChevronLeft, ChevronRight, Dumbbell } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { resolveExerciseAsset } from '../../features/ExplainerCard/exercise-data/exerciseData'
import ExerciseDetails from './ExerciseDetails'
import ExerciseGallery from './ExerciseGallery'
import './ExplainerCard.css'

/**
 * Displays a decorative catalog icon with a local failure fallback.
 * @param {object} props - Icon properties.
 * @param {string|null} [props.url] - Optional backend/external asset path.
 * @returns {import('react').ReactElement} Resolved thumbnail or dumbbell symbol.
 */
function ExerciseIcon({ url }) {
  const [failed, setFailed] = useState(false)
  const src = resolveExerciseAsset(url)
  return <span className="explainer-icon">{src && !failed
    ? <img src={src} alt="" onError={() => setFailed(true)} />
    : <Dumbbell size={20} />}</span>
}

/**
 * Renders one exercise at a time from a nonempty validated specialist response.
 * @param {object} props - Card properties.
 * @param {import('../../features/ExplainerCard/exercise-data/exerciseData').Exercise[]} props.exercises - Ordered response cards.
 * @returns {import('react').ReactElement} Exercise content with wraparound navigation.
 */
export default function ExplainerCard({ exercises }) {
  const { t } = useTranslation()
  const [activeIndex, setActiveIndex] = useState(0)
  const exercise = exercises[activeIndex]
  return <section className="explainer-card" aria-label={t('Exercise Breakdown')}>
    <header className="explainer-header">
      <ExerciseIcon key={`${activeIndex}-${exercise.icon_url}`} url={exercise.icon_url} />
      <div className="explainer-title" aria-live="polite" aria-atomic="true">
        <span>{t('Exercise Breakdown')}</span>
        <h3>{exercise.name}</h3>
      </div>
    </header>
    <ExerciseGallery key={`gallery-${activeIndex}`} exercise={exercise} />
    <ExerciseDetails key={`details-${activeIndex}`} exercise={exercise} />
    {exercises.length > 1 && <nav className="explainer-navigation" aria-label={t('Exercise Breakdown')}>
      <button type="button"
        onClick={() => setActiveIndex((activeIndex - 1 + exercises.length) % exercises.length)}>
        <ChevronLeft size={20} aria-hidden="true" /><span>{t('Previous exercise')}</span>
      </button>
      <span className="explainer-count" aria-live="polite" aria-atomic="true">{activeIndex + 1} / {exercises.length}</span>
      <button type="button"
        onClick={() => setActiveIndex((activeIndex + 1) % exercises.length)}>
        <span>{t('Next exercise')}</span><ChevronRight size={20} aria-hidden="true" />
      </button>
    </nav>}
  </section>
}
