/**
 * @file Incremental NDJSON decoder for orchestrator execution streams.
 * Fetch body chunks are not message boundaries: a UTF-8-aware buffer assembles
 * newline-delimited events. Heartbeats keep transport alive, progress drives UI
 * stages, and exactly one terminal result resolves the request. This is not SSE
 * or WebSocket transport; callers own cancellation and the overall request timeout.
 */

/**
 * Consumes progress until a validated terminal result or explicit stream failure.
 * @param {Response} response - Successful application/x-ndjson HTTP response.
 * @param {(step: {id: string, label: string, kind?: 'sql', parent?: string,
 * sql?: string, source?: string}) => void} onProgress - Publishes execution metadata.
 * @param {import('i18next').TFunction} t - Request-language translator for errors.
 * @returns {Promise<object>} Terminal result data; subsystem validation is downstream.
 * @throws {Error} For malformed events/JSON, server errors, premature EOF, or read failures.
 */
export async function readChatStream(response, onProgress, t) {
  /** @returns {Error} Localized invalid-payload error shared by validation branches. */
  const invalid = () => new Error(t('The chat API returned an invalid response.'))
  // 1. Acquire the byte reader and decoder; preserve partial lines across reads.
  if (!response.body) throw invalid()
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      // 2. Decode chunk boundaries safely, including the final unterminated line.
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      let boundary
      while ((boundary = buffer.indexOf('\n')) !== -1 || (done && buffer.length)) {
        const line = boundary === -1 ? buffer : buffer.slice(0, boundary)
        buffer = boundary === -1 ? '' : buffer.slice(boundary + 1)
        if (!line.trim()) continue
        // 3. Ignore heartbeats and publish only validated execution progress.
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
          // 4. Resolve only terminal data; errors and premature EOF remain failures.
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
    // 5. Cancel unread bytes and release the lock on success, failure, or cancellation.
    try {
      await reader.cancel()
    } finally {
      reader.releaseLock()
    }
  }
}
