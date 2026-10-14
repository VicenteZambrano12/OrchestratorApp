import { useEffect, useState } from 'react'

export function useExerciseGallery(exercise) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const media = (exercise.media_urls || []).filter(Boolean)
  const items = [
    ...media.map((url, index) => ({
      url,
      label: index === 0 ? 'Start Position' : index === 1 ? 'End Position' : 'Step {{number}}',
      number: index + 1,
      type: 'media',
    })),
    ...(exercise.anatomy_diagram_url
      ? [{ url: exercise.anatomy_diagram_url, label: 'Target Muscles', type: 'anatomy' }]
      : []),
  ]

  useEffect(() => {
    if (!isPlaying || media.length < 2) return
    const timer = setInterval(() => setActiveIndex((index) => (index + 1) % media.length), 900)
    return () => clearInterval(timer)
  }, [isPlaying, media.length])

  function select(index) {
    setIsPlaying(false)
    setActiveIndex(index)
  }

  return { items, activeIndex, isPlaying, select, setIsPlaying, mediaCount: media.length }
}
