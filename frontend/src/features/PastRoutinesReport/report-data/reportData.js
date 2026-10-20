/**
 * @file Pure validation, aggregation, and locale formatting for agent history reports.
 * Backend SQL rows contain scalar cells; these helpers derive display statistics,
 * not private model reasoning. Missing/invalid numeric measurements are excluded
 * or represented as zero according to each metric's documented behavior.
 *
 * @typedef {Object<string, string|number|null>} ReportRow
 * A backend result row; routes supply exercise/set, date, muscle, and rank columns.
 *
 * @typedef {object} PastRoutinesAnalysis
 * @property {'past_day_exercise'|'compare_last_two_workouts'|'weekly_performance'} route - Report view selector.
 * @property {string|null} day_type - Optional training split.
 * @property {string} llm_explain - Nonempty agent-written Markdown explanation.
 * @property {ReportRow[]} data - Structured scalar-only SQL results.
 *
 * @typedef {object} ReportSummary
 * @property {number} sets - Number of result rows.
 * @property {number} reps - Sum of finite numeric repetitions.
 * @property {number} volume - Sum of reps multiplied by external load.
 * @property {number|null} avgRpe - Mean of measured RPE values, or null if unavailable.
 * @property {number} exercises - Count of distinct exercise names.
 *
 * @typedef {object} ExerciseGroup
 * @property {string} name - Exercise display name.
 * @property {string|null} muscle - Primary muscle.
 * @property {number} order - Ordering key within the session.
 * @property {ReportRow[]} sets - Set-number-sorted rows.
 * @property {number} bestWeight - Maximum measured load, clamped at zero.
 * @property {boolean} bodyweight - Whether no positive external load was measured.
 * @property {number} volume - Total externally loaded volume.
 * @property {number} reps - Total measured repetitions.
 */
export const PAST_ROUTINE_ROUTES = ['past_day_exercise', 'compare_last_two_workouts', 'weekly_performance']

export const MUSCLES = ['chest', 'back', 'shoulders', 'triceps', 'biceps', 'forearms', 'core', 'quads', 'hamstrings', 'glutes', 'calves']

export const MUSCLE_COLORS = {
  chest: '#10b981', back: '#3b82f6', shoulders: '#f59e0b', triceps: '#ec4899', biceps: '#8b5cf6',
  forearms: '#64748b', core: '#14b8a6', quads: '#ef4444', hamstrings: '#f97316', glutes: '#d946ef', calves: '#0ea5e9',
}

/**
 * Tests the scalar cell contract accepted for report SQL rows.
 * @param {unknown} value - Candidate cell.
 * @returns {boolean} Whether the value is null, text, or numeric.
 */
const isCell = (value) => value === null || ['string', 'number'].includes(typeof value)

/**
 * Validates the route envelope and scalar-only row shape before report rendering.
 * @param {unknown} value - Untrusted agent response.
 * @returns {boolean} Whether the report envelope is supported.
 */
export function isPastRoutinesAnalysis(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) &&
    PAST_ROUTINE_ROUTES.includes(value.route) &&
    (value.day_type === null || typeof value.day_type === 'string') &&
    typeof value.llm_explain === 'string' && Boolean(value.llm_explain.trim()) &&
    Array.isArray(value.data) && value.data.every((row) =>
      row && typeof row === 'object' && !Array.isArray(row) && Object.values(row).every(isCell))
}

/**
 * Accepts only finite numeric measurements, without coercing SQL text cells.
 * @param {unknown} value - Candidate measurement.
 * @returns {number|null} Measured value or explicit absence.
 */
const toNumber = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null)

/**
 * Formats a muscle identifier for display.
 * @param {string|null} muscle - Raw muscle name.
 * @returns {string} Capitalized label or Unknown.
 */
export function muscleLabel(muscle) {
  return muscle ? muscle.charAt(0).toUpperCase() + muscle.slice(1) : 'Unknown'
}

/**
 * Calculates external-load volume; absent/zero reps or load contributes no volume.
 * @param {ReportRow} row - Performed-set row.
 * @returns {number} Repetitions multiplied by weight, or zero.
 */
export function setVolume(row) {
  const reps = toNumber(row.reps)
  const weight = toNumber(row.weight)
  return reps && weight ? reps * weight : 0
}

/**
 * Estimates one-repetition maximum with Epley's formula.
 * Bodyweight/unmeasured sets have no external load to project.
 * @param {ReportRow} row - Performed set with measured reps/load.
 * @returns {number} Estimated load; exact load for one rep, zero when unmeasured.
 */
export function estimatedOneRepMax(row) {
  const reps = toNumber(row.reps)
  const weight = toNumber(row.weight)
  if (!reps || !weight) return 0
  return reps === 1 ? weight : weight * (1 + reps / 30)
}

/**
 * Selects the first reported load unit, with the UI's kg display default.
 * @param {ReportRow[]} rows - Report rows.
 * @returns {string} Display unit; no load conversion is performed.
 */
export function weightUnit(rows) {
  return rows.find((row) => typeof row.weight_unit === 'string')?.weight_unit || 'kg'
}

/**
 * Aggregates measured set statistics while retaining missing RPE as null.
 * @param {ReportRow[]} rows - Performed-set rows.
 * @returns {ReportSummary} Summary statistics.
 */
export function summarize(rows) {
  const rpes = rows.map((row) => toNumber(row.rpe)).filter((rpe) => rpe !== null)
  return {
    sets: rows.length,
    reps: rows.reduce((total, row) => total + (toNumber(row.reps) || 0), 0),
    volume: rows.reduce((total, row) => total + setVolume(row), 0),
    avgRpe: rpes.length ? rpes.reduce((a, b) => a + b, 0) / rpes.length : null,
    exercises: new Set(rows.map((row) => row.exercise_name)).size,
  }
}

/**
 * Groups sets by session/order/name and preserves exercise/set ordering.
 * @param {ReportRow[]} rows - Performed-set rows.
 * @returns {ExerciseGroup[]} Ordered exercise aggregates.
 */
export function groupExercises(rows) {
  const groups = new Map()
  for (const row of rows) {
    const key = `${row.training_id ?? ''}|${row.exercise_order ?? ''}|${row.exercise_name}`
    if (!groups.has(key)) {
      groups.set(key, { name: row.exercise_name || 'Unknown', muscle: row.primary_muscle || null, order: toNumber(row.exercise_order) ?? groups.size, sets: [] })
    }
    groups.get(key).sets.push(row)
  }
  return [...groups.values()]
    .sort((a, b) => a.order - b.order)
    .map((group) => {
      const sets = [...group.sets].sort((a, b) => (toNumber(a.set_number) ?? 0) - (toNumber(b.set_number) ?? 0))
      const bestWeight = Math.max(0, ...sets.map((row) => toNumber(row.weight) || 0))
      return {
        ...group, sets, bestWeight, bodyweight: bestWeight === 0,
        volume: sets.reduce((total, row) => total + setVolume(row), 0),
        reps: sets.reduce((total, row) => total + (toNumber(row.reps) || 0), 0),
      }
    })
}

/**
 * Computes muscle shares by set count, not by load or volume.
 * @param {ReportRow[]} rows - Performed-set rows.
 * @returns {Array<{muscle: string, sets: number, share: number}>} Descending set shares.
 */
export function muscleDistribution(rows) {
  const totals = new Map()
  for (const row of rows) {
    const muscle = row.primary_muscle || 'other'
    totals.set(muscle, (totals.get(muscle) || 0) + 1)
  }
  return [...totals.entries()].map(([muscle, sets]) => ({ muscle, sets, share: sets / rows.length }))
    .sort((a, b) => b.sets - a.sets)
}

/**
 * Extracts display identity from a session's first row.
 * @param {ReportRow[]} rows - Rows belonging to one training session.
 * @returns {{date: string|null, day: string|null}} Session date/split, if available.
 */
function sessionInfo(rows) {
  const first = rows[0] || {}
  return { date: first.training_date || null, day: first.training_day || null }
}

/**
 * Compares rank-1 and rank-2 sessions by matching exercise names.
 * Bodyweight work uses repetition changes; loaded work uses volume changes.
 * Missing matches and zero baselines have null change rather than fabricated growth.
 * @param {ReportRow[]} rows - Comparison-route rows with numeric training_rank.
 * @returns {{latest: ReportSummary & {date: string|null, day: string|null},
 * previous: ReportSummary & {date: string|null, day: string|null},
 * exercises: object[], strengths: object[], weaknesses: object[]}} Comparison aggregates.
 */
export function compareWorkouts(rows) {
  const latestRows = rows.filter((row) => row.training_rank === 1)
  const previousRows = rows.filter((row) => row.training_rank === 2)
  const latest = new Map(groupExercises(latestRows).map((group) => [group.name, group]))
  const previous = new Map(groupExercises(previousRows).map((group) => [group.name, group]))
  const names = [...new Set([...latest.keys(), ...previous.keys()])]
  const exercises = names.map((name) => {
    const now = latest.get(name)
    const before = previous.get(name)
    const bodyweight = (now || before).bodyweight && (!now || !before || (now.bodyweight && before.bodyweight))
    /**
     * Chooses a comparable metric for this exercise's load category.
     * @param {ExerciseGroup} group - Session aggregate.
     * @returns {number} Repetitions for bodyweight, otherwise external-load volume.
     */
    const score = (group) => (bodyweight ? group.reps : group.volume)
    /**
     * Reduces one matched aggregate to the comparison panel's metric shape.
     * @param {ExerciseGroup|undefined} group - Optional session match.
     * @returns {{bestWeight: number, volume: number, reps: number, score: number,
     * sets: number}|undefined} Selected metrics, or an absent match.
     */
    const pick = (group) => group && { bestWeight: group.bestWeight, volume: group.volume, reps: group.reps, score: score(group), sets: group.sets.length }
    const nowStats = pick(now)
    const beforeStats = pick(before)
    const change = nowStats && beforeStats && beforeStats.score > 0 ? (nowStats.score - beforeStats.score) / beforeStats.score : null
    return { name, muscle: (now || before).muscle, bodyweight, latest: nowStats, previous: beforeStats, change }
  })
  const compared = exercises.filter((exercise) => exercise.change !== null)
  return {
    latest: { ...sessionInfo(latestRows), ...summarize(latestRows) },
    previous: { ...sessionInfo(previousRows), ...summarize(previousRows) },
    exercises,
    strengths: compared.filter((exercise) => exercise.change > 0).sort((a, b) => b.change - a.change),
    weaknesses: compared.filter((exercise) => exercise.change < 0).sort((a, b) => a.change - b.change),
  }
}

/**
 * Accumulates weekly muscle work while retaining zero entries for standard muscles.
 * @param {ReportRow[]} rows - Weekly performed sets.
 * @returns {Array<{muscle: string, sets: number, volume: number}>} Muscle aggregates.
 */
export function weeklyMuscles(rows) {
  const stats = new Map(MUSCLES.map((muscle) => [muscle, { muscle, sets: 0, volume: 0 }]))
  for (const row of rows) {
    const muscle = row.primary_muscle
    if (!muscle) continue
    if (!stats.has(muscle)) stats.set(muscle, { muscle, sets: 0, volume: 0 })
    const entry = stats.get(muscle)
    entry.sets += 1
    entry.volume += setVolume(row)
  }
  return [...stats.values()]
}

/**
 * Ranks exercises by estimated maximum, then measured load and maximum reps.
 * @param {ReportRow[]} rows - Performed-set rows.
 * @param {number} [limit=5] - Maximum ranked results.
 * @returns {Array<{name: string, muscle: string|null, bestWeight: number,
 * reps: number, e1rm: number, maxReps: number}>} Ranked exercise highlights.
 */
export function bestExercises(rows, limit = 5) {
  const best = new Map()
  for (const row of rows) {
    const name = row.exercise_name || 'Unknown'
    const current = best.get(name) || { name, muscle: row.primary_muscle || null, bestWeight: 0, reps: 0, e1rm: 0, maxReps: 0 }
    const weight = toNumber(row.weight) || 0
    const reps = toNumber(row.reps) || 0
    if (weight > current.bestWeight || (weight === current.bestWeight && reps > current.reps)) {
      current.bestWeight = weight
      current.reps = reps
    }
    current.e1rm = Math.max(current.e1rm, estimatedOneRepMax(row))
    current.maxReps = Math.max(current.maxReps, reps)
    best.set(name, current)
  }
  return [...best.values()]
    .sort((a, b) => b.e1rm - a.e1rm || b.bestWeight - a.bestWeight || b.maxReps - a.maxReps)
    .slice(0, limit)
}

/**
 * Groups measured volume and set counts into chronologically sorted date buckets.
 * @param {ReportRow[]} rows - Weekly performed sets.
 * @returns {Array<{date: string, day: string|null, volume: number, sets: number}>} Daily chart data.
 */
export function dailyVolume(rows) {
  const days = new Map()
  for (const row of rows) {
    const date = row.training_date || 'unknown'
    if (!days.has(date)) days.set(date, { date, day: row.training_day || null, volume: 0, sets: 0 })
    const entry = days.get(date)
    entry.volume += setVolume(row)
    entry.sets += 1
  }
  return [...days.values()].sort((a, b) => a.date.localeCompare(b.date))
}

/**
 * Formats an ISO-like calendar date in local calendar time without UTC day shifts.
 * @param {string|null} value - Date-prefixed string, or an absent label.
 * @param {string} language - Intl locale.
 * @param {Intl.DateTimeFormatOptions} [options] - Locale formatting options.
 * @returns {string} Formatted date, unchanged non-date label, or empty string.
 */
export function formatDate(value, language, options = { weekday: 'short', day: 'numeric', month: 'short' }) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(value)) return value || ''
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return new Intl.DateTimeFormat(language, options).format(new Date(year, month - 1, day))
}

/**
 * Formats a measured number using the selected locale.
 * @param {number} value - Display value.
 * @param {string} language - Intl locale.
 * @param {number} [digits=0] - Maximum fraction digits.
 * @returns {string} Localized number.
 */
export function formatNumber(value, language, digits = 0) {
  return new Intl.NumberFormat(language, { maximumFractionDigits: digits }).format(value)
}

/**
 * Maps a measured RPE to a semantic display class.
 * @param {number|null|undefined} rpe - Optional exertion measurement.
 * @returns {'none'|'max'|'hard'|'moderate'|'easy'} Intensity class suffix.
 */
export function rpeTone(rpe) {
  if (typeof rpe !== 'number') return 'none'
  if (rpe >= 9) return 'max'
  if (rpe >= 8) return 'hard'
  if (rpe >= 7) return 'moderate'
  return 'easy'
}
