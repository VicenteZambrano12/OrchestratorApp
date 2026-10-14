# Form frontend

A responsive React + Vite mockup for OrchestratorApp, with two views:

- **AI Chat:** example conversation, safe Markdown responses, expandable pipeline
  summaries, suggested prompts, and an optional live API connection.
- **My Routine:** a three-day demo workout with editable sets, rep targets, weights
  in kilograms, and exercise completion. Changes and saved coach recommendations
  persist in this browser's local storage; they are not synchronized to a server.

## Page structure

All JavaScript source modules under `src/` use the `.jsx` extension, including
feature hooks, helpers, and API modules. Tool configuration files retain `.js`.

[`App.jsx`](src/App.jsx) is the application entry component and renders
[`MainView.jsx`](src/pages/MainView/MainView.jsx). MainView owns the app layout,
chat state, routine persistence, and help dialog, and imports five components
from `src/components/`, each in its own folder:

- [`BrandMark`](src/components/BrandMark/BrandMark.jsx)
- [`Pipeline`](src/components/Pipeline/Pipeline.jsx)
- [`RoutinePreview`](src/components/RoutinePreview/RoutinePreview.jsx)
- [`TrainingPanel`](src/components/TrainingPanel/TrainingPanel.jsx)
- [`RoutineView`](src/components/RoutineView/RoutineView.jsx)

Each component imports its logic from a matching folder under `src/features/`,
with a subfolder per feature:

```text
src/features/
|-- BrandMark/
|   `-- appearance/
|-- Pipeline/
|   |-- expansion/
|   `-- request-status/
|-- RoutinePreview/
|   `-- plan-summary/
|-- TrainingPanel/
|   `-- weekly-progress/
`-- RoutineView/
    |-- workout-editing/
    `-- workout-completion/
```

The feature modules contain appearance configuration, pipeline stage selection
and expansion, plan summaries, weekly progress, and workout editing/completion.
Components retain their JSX and callbacks to MainView. Chat API and subsystem
renderer modules remain under `src/features/ai-chat/`.

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
