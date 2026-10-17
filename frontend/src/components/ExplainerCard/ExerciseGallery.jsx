import { useState } from 'react'
import { ChevronLeft, ChevronRight, Layers, Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useExerciseGallery } from '../../features/ExplainerCard/media-gallery/useExerciseGallery'
import { resolveExerciseAsset } from '../../features/ExplainerCard/exercise-data/exerciseData'

function ExerciseImage({ url, alt }) {
  const { t } = useTranslation()
  const [failed, setFailed] = useState(false)
  const src = resolveExerciseAsset(url)
  if (failed || !src) return <p role="status" className="explainer-image-error">{t('Exercise image unavailable.')}</p>
  return <img src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />
}

export default function ExerciseGallery({ exercise }) {
  const { t } = useTranslation()
  const { items, activeIndex, isPlaying, select, setIsPlaying, mediaCount } = useExerciseGallery(exercise)
  if (!items.length) return null
  const current = items[activeIndex]
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
