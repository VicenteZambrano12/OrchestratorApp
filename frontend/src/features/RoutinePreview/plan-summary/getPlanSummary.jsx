export function getPlanSummary(demo) {
  return {
    title: demo ? 'Your next chapter starts here' : 'Your coach’s recommendation',
    description: demo ? '3-day Push / Pull / Legs · Example plan' : 'Markdown plan · Ready to review',
  }
}
