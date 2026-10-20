/**
 * @file Catalog movement/anatomy image gallery with frame-based rep animation.
 * Playback is local timer-driven image selection, not streamed agent output.
 * Missing/failed media is isolated to an image status rather than failing the card.
 */
import { useState } from 'react'
import { ChevronLeft, ChevronRight, Layers, Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useExerciseGallery } from '../../features/ExplainerCard/media-gallery/useExerciseGallery'
import { resolveExerciseAsset } from '../../features/ExplainerCard/exercise-data/exerciseData'

/**
 * Loads a supported media asset and exposes an accessible image-failure state.
 * @param {object} props - Image properties.
 * @param {string} props.url - Catalog asset path or supported image URL.
 * @param {string} props.alt - Exercise/frame-specific alternative description.
 * @returns {import('react').ReactElement} Lazy image or unavailable status.
 */
function ExerciseImage({ url, alt }) {
  const { t } = useTranslation()
  const [failed, setFailed] = useState(false)
  const src = resolveExerciseAsset(url)
  if (failed || !src) return <p role="status" className="explainer-image-error">{t('Exercise image unavailable.')}</p>
  return <img src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />
}

/**
 * Renders frame selection and optional autoplay from the exercise-gallery hook.
 * @param {object} props - Gallery properties.
 * @param {import('../../features/ExplainerCard/exercise-data/exerciseData').Exercise} props.exercise - Validated media data.
 * @returns {import('react').ReactElement|null} Gallery, or null when no media exists.
 */
export default function ExerciseGallery({ exercise }) {
  const { t } = useTranslation()
  const { items, activeIndex, isPlaying, select, setIsPlaying, mediaCount } = useExerciseGallery(exercise)
  if (!items.length) return null
  const current = items[activeIndex]
  /**
   * Localizes a frame/anatomy label with its optional step number.
   * @param {{label: string, number?: number}} item - Hook-generated gallery item.
   * @returns {string} Translated item label.
   */
  const label = (item) => t(item.label, { number: item.number })

  return <section className="explainer-gallery" aria-label={t('Exercise images')}>
    <div className="explainer-image">
      <ExerciseImage key={current.url} url={current.url} alt={`${exercise.name} - ${label(current)}`} />
      <span className="explainer-image-label"><Layers size={14} />{label(current)}</span>
      {mediaCount > 1 && current.type === 'media' && <button type="button"
        className="explainer-play" aria-pressed={isPlaying} onClick={() => setIsPlaying(!isPlaying)}>
        {isPlaying ? <Pause size={13} /> : <Play size={13} />}
        {t(isPlaying ? 'Pause Rep' : 'Animate Rep')}
      </button>}
      {items.length > 1 && <>
        <button type="button" className="explainer-image-prev" aria-label={t('Previous image')}
          onClick={() => select((activeIndex - 1 + items.length) % items.length)}><ChevronLeft size={18} /></button>
        <button type="button" className="explainer-image-next" aria-label={t('Next image')}
          onClick={() => select((activeIndex + 1) % items.length)}><ChevronRight size={18} /></button>
      </>}
    </div>
    {items.length > 1 && <div className="explainer-media-options">
      {items.map((item, index) => <button key={`${item.url}-${index}`} type="button"
        aria-pressed={index === activeIndex} onClick={() => select(index)}>{label(item)}</button>)}
    </div>}
  </section>
}
