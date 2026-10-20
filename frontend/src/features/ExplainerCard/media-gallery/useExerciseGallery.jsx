/**
 * @file Local image-gallery state for agent-generated exercise cards.
 * Simulated movement playback advances catalog frames every 900 ms; anatomy is
 * selectable but excluded from autoplay. No video/streaming backend is involved.
 */
import { useEffect, useState } from 'react'

/**
 * Builds gallery items and controls selection/playback for one mounted exercise.
 * @param {import('../exercise-data/exerciseData').Exercise} exercise - Validated card data.
 * @returns {{items: Array<{url: string, label: string, number?: number, type: string}>,
 * activeIndex: number, isPlaying: boolean, select: (index: number) => void,
 * setIsPlaying: import('react').Dispatch<import('react').SetStateAction<boolean>>,
 * mediaCount: number}} Gallery data and local actions.
 */
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
    // 1. Allocate playback only when requested and at least two movement frames exist.
    if (!isPlaying || media.length < 2) return
    // 2. Cycle movement frames and clear the timer when playback stops or count changes.
    const timer = setInterval(() => setActiveIndex((index) => (index + 1) % media.length), 900)
    return () => clearInterval(timer)
  }, [isPlaying, media.length])

  /**
   * Stops autoplay so explicit user selection remains stable.
   * @param {number} index - Gallery item index, including optional anatomy.
   * @returns {void}
   */
  function select(index) {
    // 1. Disable timer-driven movement before applying the user's selected item.
    setIsPlaying(false)
    setActiveIndex(index)
  }

  return { items, activeIndex, isPlaying, select, setIsPlaying, mediaCount: media.length }
}
