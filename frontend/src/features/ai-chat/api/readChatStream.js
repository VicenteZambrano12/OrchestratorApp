export async function readChatStream(response, onProgress, t) {
  const invalid = () => new Error(t('The chat API returned an invalid response.'))
  if (!response.body) throw invalid()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      let boundary
      while ((boundary = buffer.indexOf('\n')) !== -1 || (done && buffer.length)) {
        const line = boundary === -1 ? buffer : buffer.slice(0, boundary)
        buffer = boundary === -1 ? '' : buffer.slice(boundary + 1)
        if (!line.trim()) continue
        const event = JSON.parse(line)
        if (!event || typeof event !== 'object') throw invalid()
        if (event.type === 'heartbeat') continue
        if (event.type === 'progress') {
          if (typeof event.id !== 'string' || !event.id.trim() ||
            typeof event.label !== 'string' || !event.label.trim()) throw invalid()
          const step = { id: event.id, label: event.label }
          if (event.kind !== undefined) {
            if (event.kind !== 'sql' || !['parent', 'sql', 'source'].every(
              (key) => typeof event[key] === 'string' && event[key].trim(),
            )) throw invalid()
            Object.assign(step, { kind: event.kind, parent: event.parent, sql: event.sql, source: event.source })
          }
          onProgress(step)
        } else if (event.type === 'result') {
          if (!event.data || typeof event.data !== 'object') throw invalid()
          return event.data
        } else if (event.type === 'error') {
          if (![422, 500].includes(event.status)) throw invalid()
          const error = new Error(t('The chat API returned HTTP {{status}}. Check that the backend is running and your request is valid.', { status: event.status }) +
            (event.status === 422 && typeof event.message === 'string' ? ` ${event.message}` : ''))
          error.backendDown = event.status >= 500
          throw error
        } else {
          throw invalid()
        }
      }
      if (done) throw new Error(t('The progress stream ended before the response was ready. Please retry.'))
    }
  } finally {
    try {
      await reader.cancel()
    } finally {
      reader.releaseLock()
    }
  }
}
