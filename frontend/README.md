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

AI Chat fills the viewport with an anchored composer. The conversation scrolls
independently of the input bar, and new messages scroll only the conversation,
not the page. On desktop, the training panel has its own scroll area. My Routine
continues to use normal page scrolling.

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

Live chat calls `POST /{sessionId}/chat` with `{ query, language }`, where
`language` is `"EN"` or `"ES"` according to the selected UI language.
The selected profile also supplies `user_id`, which Routine Maker requires.
Routine JSON is displayed as training days with focus, info, catalog exercise
names/IDs, sets, repetitions and rest. A draft is not saved automatically:
**Save routine to database** sends a separate confirmation turn. Saved routines
are new inactive SQLite versions, preserving previous routines and active selection.
Copying a saved recommendation into **My Routine** is still a browser-local action.
Sessions use the selected user's ID and hold process-local conversation context.
Errors are displayed explicitly.
The initial conversation and editable workout remain labeled demo content even
when live mode is selected.

## Users and sessions

Both profile buttons open the same user picker, including the header button on
mobile. Select an existing profile or register a username and preferred weight
unit, then switch. Profiles persist in SQLite via `GET /users` and `POST /users`;
duplicate usernames return HTTP 409. These profiles are not authenticated accounts.
The weight-unit preference is stored with the profile; the demo workout remains
in kilograms.

On page load the lowest-ID user is the default. Listing an empty database creates
one default profile, Jamie Davis. The selected user's ID (as a string) is the
session ID. Startup and every switch await `POST /{userId}/key` before activating
the profile. Failures are visible and retryable; failed switches keep the current
user. Chat includes the selected numeric `user_id` automatically.

Switching profiles clears the visible conversation and isolates browser-saved
demo routines under `form-routine-v1:{userId}`. Previous unscoped local storage is
left untouched. Returning to a user reuses their backend session context;
**New conversation** calls `POST /{userId}/key?reset=true` to clear that user's
conversation memory and pending routine draft, without deleting saved routines.

## Language

The header **EN / ES** toggle switches the interface and suggested prompts using
`i18next` and `react-i18next`. Dictionaries live in
[`en.json`](src/i18n/languages/en.json) and
[`es.json`](src/i18n/languages/es.json). The shared i18n instance is initialized
in [`src/i18n/index.jsx`](src/i18n/index.jsx).

The preference persists as `form-language` in local storage. On first visit,
Spanish browser locales (including `es-ES`) select Spanish; other locales use
English. The root HTML `lang` attribute follows the active language. The language
toggle is also available on the server-unavailable screen.

Each chat request captures the active language as uppercase `EN` or `ES`.
Switching languages does not reset the chat or routine, translate existing
messages, or alter an in-flight request. Future requests (including retries) use
the newly selected language. Saved exercise data and recommendations remain
unchanged; only built-in workout labels are translated for display.

## Pipeline and subsystem rendering

Demo pipeline stages are illustrative. The current API does not stream
intermediate events, so live mode shows request-in-progress status and the final
selected subsystem, not inferred reasoning or fabricated intermediate results.

Exercise explainer arrays render as HTML through the reusable
[`ExplainerCard`](src/components/ExplainerCard/ExplainerCard.jsx) React component.
Cards are centered within the message. Multiple exercises have large, labeled
previous/next buttons and a position counter in a dedicated footer. Each card includes a media/anatomy
gallery, optional repetition animation, and coach insight, execution, and overview
views. Gallery state and animation reset when changing exercises. Missing images
show an explicit unavailable message. UI labels support English and Spanish;
catalog text and personalized explanations are preserved.

Parsing, payload validation, asset resolution, and the gallery hook live under
`src/features/ExplainerCard/`. Stored `database/images/...` paths resolve through
the same API base URL as chat; the backend serves `/database/images`. The `/api`
production reverse proxy must forward these image requests too.

Other answers, including explainer clarification strings, use `react-markdown`
without raw HTML support. The renderer registry in
[`SubsystemResponse.jsx`](src/features/ai-chat/components/SubsystemResponse.jsx)
selects the exercise card or Markdown template. Do not insert untrusted HTML directly.

Created or updated routine responses can be saved as Markdown recommendations
in My Routine. They do not silently replace the structured demo exercise log:
the backend currently returns routine text, not a structured exercise list.

## Appearance

The header sun/moon button toggles Light and Dark; the adjacent selector also
offers System, which follows OS appearance changes. The preference persists as
`form-theme` in local storage and synchronizes across tabs. An early head script
applies the root `.dark` class before first paint. Storage failures are reported
without preventing an in-memory theme change.

Semantic palettes live in `src/theme.css`, shared by chat, routines, loading,
dialogs, and error screens. Light mode uses neutral canvas/white cards and a
forest promo anchor; dark mode uses obsidian/forest surfaces. Tailwind v4's
class-based dark variant is configured in `src/index.css`. Preflight is omitted
to preserve the existing component styles and layout.

## Checks

```sh
npm run lint
npm run build
npm run test:i18n
```
