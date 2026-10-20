# Form frontend

A responsive React + Vite application for OrchestratorApp, with two views:

- **AI Chat:** safe Markdown responses, always-visible live workflow steps,
  suggested prompts, and a live API connection. Each executed node adds one short
  phrase to the timeline; no expansion or simulated progress timers are used.
  The chat requests `Accept: application/x-ndjson` from `POST /{id}/chat`, receives
  `progress` events followed by a `result` (the existing JSON response envelope)
  or an explicit `error`, and keeps the steps with the answer. Heartbeats keep
  long-running requests alive. English and Spanish labels follow the UI language.
  Older JSON-only servers still return answers, without invented node steps.
  The three suggested prompts cover the integrated subsystems: creating a
  muscle-building routine, explaining exercise technique, and analyzing saved
  workouts from the last seven days. Prompts follow the selected UI language.
- **My Routine:** loads the selected user's active saved plan through
  `GET /users/{userId}/routine` and uses the original workout view, not the chat
  routine card. It shows the saved days, exercises, sets, rep targets, rest, notes,
  summary, and recovery guidance. Weights start at zero because the saved plan
  does not contain weights. Edits stay local until the user confirms an update;
  weights and completion are saved as workout sets only after finish confirmation.
  Loading, errors, retry, and
  profiles without an active routine have explicit states.

### Source documentation

JavaScript and JSX modules begin with `@file` JSDoc describing their UI or
infrastructure role. Components and hooks document their props/options, state
dependencies, and return values; shared data contracts use JSDoc typedefs beside
their validators and adapters rather than introducing runtime interfaces.
Numbered comments explain lifecycle, cancellation, mutation, and recovery flows.
Keep these contracts aligned with implementation when changing behavior, especially
NDJSON event handling, routine draft confirmation, and actual-set persistence.
Framer Motion owns startup and dialog entry/exit transitions. CSS owns smaller
visual feedback; gallery and workflow playback timers never control backend execution.

### Responsive UI and accessibility

The shared `src/workspace.css` foundation coordinates the application shell,
44px minimum controls, visible keyboard focus, skip navigation, readable text,
safe-area spacing, and wrapping content. Feature-specific styles own card,
exercise, report, and chart layouts.

- **Mobile first:** chat, navigation, training content, exercise inputs, and report
  sections stack instead of overflowing or hiding features. Wider layouts use
  48rem, 64rem, and 80rem breakpoints. The desktop chat shell contains scrolling
  only when enough horizontal and vertical space is available.
- **Dialogs:** `AdaptiveDialog` keeps native focus trapping, Escape/backdrop
  dismissal, pending-save locks, and focus restoration. It slides up as a mobile
  sheet and centers on larger screens. `AnimatePresence` retains it until exit
  finishes; reduced-motion preferences disable the transition.
- **Theme:** new visitors start in dark mode. Saved light/dark/system preferences
  and cross-tab synchronization still apply. Shared text/control colors are
  contrast-tested in both themes; data and error labels do not rely on color alone.
- **Resilient data:** mobile routine rows become labeled cards, day selectors wrap,
  report metrics remain visible, and long headings/errors reflow at 200% text size.
- **Workflow:** when graph scaling would shrink node controls below usable text
  sizes, all nodes appear as a selectable, unscaled list. Narrow popup windows
  stack node selection and results.

Run `npm run test:ui` after `npx playwright install chromium` for browser checks
at 375, 768, 1024, and 1440px. `npm run test:startup` runs the focused startup
suite. Tests cover touch targets, overflow, focus restoration, reduced motion,
long text, EN/ES, theme preferences, routine updates, failed-workout recovery,
structured responses, and solid-surface text contrast. Gradient/image-backed
surfaces also need visual review; browser checks are not a WCAG certification.

### Frontend observability

The shared logger in `src/lib/observability/logger.js` writes structured browser
console records with UTC timestamps, severity, scope, and stable event names.
Set `VITE_LOG_LEVEL=debug|info|warn|error|off` before starting Vite or building.
The default is `debug` in development and `warn` in production; invalid values
fail explicitly. `configureLogging(level)` can change the threshold at runtime.

Use `createLogger('module')` with static event names and metadata. Only `method`,
`route`, `status`, `duration_ms`, `outcome`, and `error_type` are retained.
Route labels must be static templates, never actual URLs. Never put private data
in scopes, event names, or metadata values. Use `errorType(error)` rather than
logging error objects, messages, stacks, or rejection reasons.

All application API requests use `observedFetch(routeTemplate, url, options)`.
It preserves fetch responses/errors and records timing until response headers,
HTTP status, and network failures. HTTP 4xx logs at `warn`, 5xx/network failures
at `error`, intentional cancellation at `debug`, and timeouts at `warn`.
Chat also times response decoding, including NDJSON stream consumption, and
records stream/parse failures through `observeOperation`. It does not consume
responses twice or delay streaming callbacks.

Startup registers uncaught-error and unhandled-rejection listeners once, with
cleanup on Vite hot disposal. A React error boundary wraps both the theme
provider and application, logs render/lifecycle failures, and shows a localized
reload screen. Reloading can lose unsaved changes. Existing handled-error UI
and retry behavior are preserved.

No logs are persisted or sent to a backend or third-party service. The module
does not record request/response bodies, headers, user/session identifiers,
query strings, raw error messages, or stacks. Browser/React developer diagnostics
remain independent of this module.

Run `npm run test:observability` for logging, timing, cancellation, privacy,
listener lifecycle, and React error-boundary tests.

### Live system map

Use **Live system map** in the header to open a separate, resizable browser window.
Move it independently (including to another display) while using chat. It stays
connected to the latest request, including when opened midway through a response.
The entire tree, including optional branches, SQL, a shared database, and the response node,
is visible before execution. The connected tree automatically scales to fit its
panel at every window size; it never switches to a flat list. This overview
intentionally scales node labels and hit areas with the diagram to preserve the
original full-tree presentation. No nodes are added as execution progresses.
One cylinder-shaped database node in the top-left corner connects to all three SQL branches. Each
connection highlights independently, so using one branch does not mark the other
database connections as executed. Selecting the database shows its source label,
without exposing bound values or database rows.
Repeated queries and per-exercise explanations reuse their stage nodes; every
individual event remains available in the right-hand execution log.

Executed routes glow, the current node animates, unused subsystem branches remain
muted, and failures mark the interrupted node. Visual playback advances once per
second, including a separate step for each SQL source; this never delays network
requests or the chat answer. The status shows **Playing execution** if the API has
already finished but the visualization is catching up. The right-hand panel shows
the chat and routine-save API responses as soon as they arrive, the selected/current node's details,
and execution events as playback reveals them. Results stack below the tree
on narrow windows; SQL and JSON wrap rather than producing horizontal scrollbars.
The map resets for each request or new conversation, closes when switching users,
and follows the application's theme and language. Allow pop-ups for this site if
the browser blocks the window.

SQL events cover chat's history SQL client, exercise catalog, and routine repository.
SQL event parameters, result rows, absolute database paths, and private model reasoning
are not exposed. The normal chat API response is shown unchanged and may include
the selected user's workout rows. Database source nodes identify the actual SQLite file used, not a guessed
source. A direct routine-save button shows its save stage but does not invent SQL
events for the separate, non-streaming save endpoint. JSON-only servers explicitly
show that execution events are unavailable.

### Workout controls

The **A little stronger. Every single week.** card loads the selected user's
active plan from `GET /users/{userId}/routine`. Weekly frequency is the number
of planned days; **Max session duration** is the longest planned session in minutes,
matching the backend's routine timing convention. For legacy templates without
saved timing, the card shows **Estimated max session**, calculated only from
planned sets: 5 minutes of warm-up, 45 seconds per working set, 90 seconds of
rest between sets, and 1 minute between exercises, rounded up to whole minutes.
The card uses the longest estimated day, and its tooltip explains these assumptions.
Recorded workout times and activity history never affect planned or estimated
duration. The estimate does not modify the saved routine or its timing.
Loading, missing routines, and retryable
errors are explicit. Saving a new routine in chat refreshes these stats.

**Your weekly rhythm** loads `GET /users/{userId}/days` for the selected user.
It displays the last seven UTC dates in chronological order, ending with today
(Sunday through Saturday when today is Saturday). Markers reflect logged
workouts, not scheduled template days or unsaved exercise checkboxes. The count
shows training days logged. Weekday labels follow the selected English/Spanish
language. Loading and retryable errors are explicit; returning to AI Chat after
a workout reloads the history.

Run `node --test src/components/TrainingPanel/weekly-rhythm.test.js` to check
routine day counts, maximum durations, refresh after saving, legacy plans,
history ordering, markers, localization, loading, errors, and user isolation.

Routine details appear as compact badges, and each day card shows its completion
count. Before starting, sets, rep targets, and weights are editable; a zero working
weight displays `-- kg`. Invalid values show an error rather than a saved message.

**Start Workout** starts the selected day's elapsed timer and expands every
exercise into its individual sets, with actual reps and weight inputs available
immediately. Enter results as you train; rep inputs start empty instead of guessing
from prescribed rep targets. Targets remain visible but are read-only during the
workout. Checking an exercise starts its prescribed rest
countdown, with **+15s** and **Skip** controls. Other days are disabled for mouse
and keyboard navigation until the current workout is saved. Visiting AI Chat and
returning preserves the active day, timer, completion, and all entered set values without reloading the
routine. Routine structure editing is disabled during a workout.

**Finish workout** opens a confirmation-only dialog; it contains no set inputs.
Only filled sets from exercises marked Done are submitted, using values already
entered inline. Leave reps blank to skip individual sets or an entire exercise,
even when a working weight is prefilled. Partially completed exercises can be
marked Done. At least one filled set in an exercise marked Done is required.
Provided reps must be positive whole numbers; provided weights must be
non-negative. Blank weights are saved as null, not zero.
Weights use the selected profile's kg/lbs preference. **Keep working out** closes
the dialog without ending the session or making a request. **Yes, finish and save**
calls `POST /users/{userId}/workouts` with the loaded routine's database ID and
performed sets. The routine ID comes from the `X-Routine-Id` header returned by
routine GET/PUT responses. Cross-origin deployments must expose this header.
The server assigns the workout ID, set numbers, and UTC save date. Saving is blocked
when no filled sets belong to exercises marked Done or provided values are invalid.
While saving, repeat submits
and dismissal are disabled. Errors preserve the dialog and actual values for
retry; only success ends the timer, unlocks days, and shows a saved message.
Starting the next workout clears that day's previous completion marks.

**Edit workout** reveals drag handles, move-up/down controls (also usable on touch
screens), swap/remove actions, and an add-exercise bar. Focus a drag handle and use
the up/down arrow keys for keyboard reordering. Add/swap opens a dialog with
suggestions from the current routine and support for custom exercise names.
**Done editing** opens a confirmation dialog explaining that the edited plan will
become a new active routine and the previous version will be kept inactive.
**Keep editing** closes the dialog without saving or discarding edits.
**Yes, update routine** sends the complete edited plan to
`PUT /users/{userId}/routine`, without chat/draft query parameters. Only a
successful save exits editing and displays a saved confirmation. While saving,
duplicate submissions and dismissal are disabled; errors remain visible in the
dialog so the user can retry without losing edits.

Catalog exercise IDs are retained through loading, reordering, adding, and
swapping suggested exercises. Custom exercise names may still be used locally,
but cannot be saved until replaced by a catalog-backed suggestion. Empty days,
duplicate exercises, and invalid targets cannot be saved. Weights and exercise
completion are not included in the saved routine; completed sets are persisted
separately through the finish-workout flow.

Run `npm run test:routine-update` for the interactive routine/workout confirmation,
day locking, actual-set submission, and cancel/retry
tests and `npm run test:i18n` for routine conversion, API, and localization tests.

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
In chat, routine JSON is displayed as training days with focus, info, catalog exercise
names/IDs, sets, repetitions and rest. A draft is not saved automatically:
**Save routine to database** sends the complete preview to
`PUT /users/{userId}/routine`, with `session_id`, `draft_id`, and `language`
as query parameters, without another LLM call. Chat sends
`client_saves_routine: true`; when the backend recognizes an explicit save
confirmation, it returns `save_requested` without writing the database, and the
frontend uses the same PUT save flow. Ordinary previews, refusals, and requests
for changes do not trigger PUT.
The draft identity keeps retries from creating duplicate versions and rejects
stale or mismatched previews. A saved confirmation is shown only after PUT
succeeds. Failed chat saves retain the preview and a Save button for retry,
without resending the chat message or invoking the model again. Successful saves
immediately update the loaded active routine and reset session-only workout edits.
Saved routines are new active SQLite versions, preserving and deactivating previous
versions. Opening **My Routine** fetches the current active version from the backend.
Sessions use the selected user's ID and hold process-local conversation context.
Errors are displayed explicitly.

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

Switching profiles clears the visible conversation and session-only workout edits.
Old browser-saved demo routines are not used as active plans. Returning to a user
reuses their backend session context;
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
applies the root `.dark` class before first paint. New visitors default to Dark;
saved Light and System selections take precedence. Storage failures are reported
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
npm run test:ui
```
