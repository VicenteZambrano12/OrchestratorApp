# Form frontend

A responsive React + Vite mockup for OrchestratorApp, with two views:

- **AI Chat:** example conversation, safe Markdown responses, expandable pipeline
  summaries, suggested prompts, and an optional live API connection.
- **My Routine:** a three-day demo workout with editable sets, rep targets, weights
  in kilograms, and exercise completion. Changes and saved coach recommendations
  persist in this browser's local storage; they are not synchronized to a server.

## Run

```sh
npm install
npm run dev
```

Demo mode is enabled by default and does not call an AI provider. Switch the
header selector to **Live API** to connect to the backend. The Vite development
server proxies `/api` to `http://127.0.0.1:8000`. For a deployed frontend, configure
a same-origin `/api` reverse proxy, or set `VITE_API_BASE_URL` to a backend base
URL with appropriate CORS support. Do not put provider credentials in Vite variables.

Live chat calls `POST /{sessionId}/chat` with `{ query, language: "EN" }`.
Sessions are local conversation identifiers; the backend is stateless. Include
relevant routine/history details in each request. Errors are displayed explicitly.
The initial conversation and editable workout remain labeled demo content even
when live mode is selected.

## Pipeline and subsystem rendering

Demo pipeline stages are illustrative. The current API does not stream
intermediate events, so live mode shows request-in-progress status and the final
selected subsystem, not inferred reasoning or fabricated intermediate results.

All subsystem answers currently use `react-markdown` without raw HTML support.
The renderer registry in
[`SubsystemResponse.jsx`](src/features/ai-chat/components/SubsystemResponse.jsx)
is the extension point for future React templates for the routine maker,
exercise explainer, and progress analyzer. Do not insert untrusted HTML directly.

Created or updated routine responses can be saved as Markdown recommendations
in My Routine. They do not silently replace the structured demo exercise log:
the backend currently returns routine text, not a structured exercise list.

## Checks

```sh
npm run lint
npm run build
```
