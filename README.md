# OrchestratorApp

## Backend structure

T

Empty folders are retained with `.gitkeep` files. Python-generated
`__pycache__` folders are excluded by `.gitignore`.

## Running the backend

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
From the repository root:

```bash
uv sync --project backend --locked
uv run --project backend --locked uvicorn app:app --app-dir backend/src --reload
```

Dependencies are declared in `backend/pyproject.toml` and pinned in
`backend/uv.lock`. `uv sync` creates the backend's `.venv` automatically; manual
activation is not required. To add a dependency, run
`uv add --project backend <package>`, and commit both the manifest and lockfile.

The FastAPI application is defined in `backend/src/app.py` and imports the health
and chat routers from `backend/src/api/Endpoint/`. `GET /health`
which returns HTTP 200 with `{"status": "ok"}`. Interactive API documentation is
available in Swagger UI at `http://127.0.0.1:8000/docs` and ReDoc at
`http://127.0.0.1:8000/redoc`; the OpenAPI schema is served at
`http://127.0.0.1:8000/openapi.json`. The schema groups endpoints into Chat and
Health and includes field descriptions, full payload examples, and actual error
formats. API version metadata is `0.1.0`; no project license is currently declared.
App metadata (title, summary, version, Markdown description, contact, license, and
tags) lives in `backend/src/api/documentation.yaml` and is loaded at startup
relative to its Python loader, independently of the working directory. Invalid
or missing metadata fails startup explicitly. Restart the backend after editing
this YAML file.
Neither endpoint requires authentication. Provider credentials are configured
on the server and must not be included in client requests. `/health` is a liveness
check only: it does not validate provider readiness.

## Gemini connectivity diagnostic

To isolate provider failures from routing and chat processing, make one harmless
Gemini call using the same server configuration:

```bash
uv run --project backend --locked python backend/src/check_gemini_api.py
```

The script reads `GEMINI_API_KEY` and `LLM_MODEL` using the existing Gemini client
and sends only `Reply with exactly: Gemini connectivity OK`. It prints the
configured model and generated answer, or the HTTP status, provider error body,
and `Retry-After` header when present. API keys are redacted from error messages.
It does not retry; successful calls consume provider quota. Exit status is 0 on
success and 1 for configuration, network, or provider errors. Use
`--model gemini-2.5-flash-lite` to override the model for this diagnostic only.

The Gemini client defaults to text output for answers and orchestrator IDs.
Structured decision stages explicitly request `application/json`: Exercise
Explainer and Past Routines Analyzer parameter decisions, and Routine Maker
routing decisions. This prevents Markdown code fences around JSON; existing
Pydantic validation still checks the content and rejects invalid decisions.

## Chat endpoint

`POST /{id}/chat` requires a caller-supplied session ID as a single URL path
segment and accepts two required JSON fields: `query`, a non-empty
string, and `language`, either `ES` or `EN`. `user_id` is additionally required
for Routine Maker and must identify an existing SQLite user. It is not
authentication. Request and response models are
defined in separate `ChatRequest.py` and `ChatResponse.py` files in
`backend/src/api/DataClasses/pipeline/`; the endpoint is defined
separately in `backend/src/api/Endpoint/chat.py` and imported by the app.

With the backend running:

```bash
curl -X POST http://127.0.0.1:8000/session-20261014-morning-workout/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"Explain how to perform a squat","language":"EN"}'
```

The endpoint routes and executes the query with `Pipeline`, returning HTTP 200
with `{"subsystem": "exercise_explainer", "response": "..."}` for text results.
The required `subsystem` field is the orchestrator's selected ID:
`routine_maker`, `exercise_explainer`, `past_routines_analyzer`, or `no_system`
for localized no-match messages. Routing executes once per request.
Routine Maker results remain structured under `response`, with
`status`, `parameters`, `message`, structured `routine`, `routine_id`, and `draft_id` fields.
Drafts are cached per session/user and require an explicit later confirmation
before a new active routine version is saved. The preview's `draft_id` can be
confirmed through `POST /{id}/routine/save` without any LLM calls. Exercise explanations
return an exercise list under `response`, or a text clarification request.
Invalid request bodies
return HTTP 422. Configuration, provider, and processing failures propagate
through FastAPI's HTTP 500 handling rather than returning a successful answer.
HTTP 422 responses use a JSON `detail` array; unhandled HTTP 500 responses use
plain text (`Internal Server Error`) in non-debug deployments. The API does not
introduce a custom error envelope or application-level 400/401/403/404 responses.
Default pipeline execution requires Gemini configuration and incurs API usage.
The session ID is opaque: it is not an authentication credential, is not checked
against a session store. The endpoint uses the latest two stored turns for
follow-ups and stores successful responses in process-local session memory,
which is lost on restart. It has no explicit history or routine-state input;
those remain available through the Python pipeline interface. The former `POST /chat` URL now returns
HTTP 404; clients must include the session ID in the path.

Run endpoint and OpenAPI documentation tests without live API calls:

```bash
PYTHONPATH=backend/src:backend/tests uv run --project backend --locked python -m unittest test_chat_endpoint test_openapi -v
```

## Orchestrator routing

To route using Gemini, configure `GEMINI_API_KEY` and `LLM_MODEL` in the
repository-root `.env`, then use:

```python
from systems.orch.Orchestrator import Orchestrator

orchestrator = Orchestrator.from_gemini()
target = orchestrator.route({"query": "Make me a three-day gym routine"}, language="ES")
```

`from_gemini()` creates a reusable `GeminiClient`, loads the existing YAML
prompt, and sends the routing rules as Gemini's `systemInstruction`. It strips
surrounding whitespace from the returned ID before validating the selection.
Every routing interface uses Pydantic to require a string matching exactly one
ID in the current subsystem list or the reserved `no_system` ID. The model
returns `no_system` when none of the available subsystems can handle the query,
rather than forcing an unrelated query into the closest system.
Invalid selections retry up to three total
LLM calls (the initial call plus two retries), stopping at the first valid ID.
Three invalid responses raise `ValueError` with the Pydantic validation error
as its cause; there is no fallback selection. Invalid input, configuration
errors, and API failures are not retried. Retried calls also consume API quota.
API errors propagate to the caller; routing does not execute the selected system.
You can inject an existing client with `Orchestrator.from_gemini(client)`.
The factory also accepts `prompt_path` and `systems_path` overrides.
Backend examples require `backend/src` on `PYTHONPATH`.

To run the live routing smoke test from the repository root:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_orchestrator.py
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_orchestrator.py "How do I perform a squat?" --language EN
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_orchestrator.py "What is the capital of Japan?" --language EN
```

The script loads your key and model from `.env`, makes a real Gemini request,
and prints only the selected subsystem ID, for example `exercise_explainer`.
For `no_system`, it additionally prints the default message in the requested
language, loaded from `backend/src/config/prompts/nosystem/nosystem.yaml`.
Backend callers can retrieve that message with
`Orchestrator.no_system_message(language)`; `route()` still returns only the ID.
It does not execute the subsystem. API usage and quota apply; errors go to stderr
and return exit status 1. Use `--language ES` for Spanish.

`backend/src/systems/orch/Orchestrator.py` defines the pipeline's routing entry
point and imports its routing utilities from
`backend/src/utils/orch/func/`, with one utility function per file named after
that function. The routing-selection validation model lives in
`backend/src/utils/orch/dataclass/models.py`. Prompt loading, provider
adaptation, request validation, and no-match messages are implemented there;
the existing class interface is unchanged.
Construct `Orchestrator(selector)` with a callable that accepts
`(query, subsystems, language)` and returns a configured subsystem's `id` or `no_system`. The callable
is where your AI provider makes its decision using the subsystem descriptions.
This injected-selector interface remains available alongside `from_gemini()`.

To use the YAML routing prompt, construct the orchestrator with
`Orchestrator.from_chat_model(chat_model)`. The `chat_model` callable receives
a list of system/user message dictionaries (`role` and `content`) and must
return the model's response text containing the selected subsystem ID.

```python
from systems.orch.Orchestrator import Orchestrator

orchestrator = Orchestrator.from_chat_model(chat_model)
target = orchestrator.route({"query": "Make me a three-day gym routine"}, language="ES")
```

Supply your provider adapter as `chat_model`.
The factory loads `backend/src/config/prompts/orchestrator/orchestrator.yaml`
independently of the working directory and fills `{payload}` with validated
query/subsystem/language JSON. An optional `prompt_path` argument selects another YAML
file. Prompt configuration is loaded once when the factory is called.

When a request omits `subsystems`, the orchestrator reads
`backend/src/config/systems.json` and uses its three gym systems: Routine Maker,
Exercise Explainer, and Past Routines Analyzer. The default registry path is
independent of the working directory. The constructor, `from_chat_model`, and
`from_gemini` accept an optional `systems_path` for another registry.
The registry is read and validated on each request that omits `subsystems`.
Missing or unreadable registry files raise their file errors; malformed JSON
or invalid subsystem entries raise `ValueError` before calling the AI model.

Call `orchestrator.route(payload)` with a JSON string or a parsed object:

```json
{"query": "How do I perform a squat?", "language": "EN"}
```

The `language` parameter accepts exactly `ES` (Spanish) or `EN` (English).
An explicit parameter overrides the request's `language` field; when both are
omitted, the default is `EN`. Other values raise `ValueError`. The registry's
top-level `language` field maps these codes to their language names.
The model prompt includes the selected language, but the result contains only
the unchanged subsystem ID. The caller must pass the language separately to
any downstream system. Routing does not generate or translate the gym answer.

An explicit `subsystems` list in the request overrides the file-backed registry.
Each entry must contain a unique `id` and a non-empty `description`.

The result is the selected subsystem's ID or `no_system` as a string, not its
configuration or a generated answer. Routing does not execute the subsystem or expose
an HTTP endpoint. Invalid input, duplicate IDs, and unknown selections raise
`ValueError`; AI provider errors propagate to the caller.

Run the routing tests from the repository root:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python -m unittest discover -s backend/tests -p test_orchestrator.py -v
```

## Pipeline

`backend/src/systems/pipeline/Pipeline.py` combines routing and system execution.
It uses the existing `Orchestrator` class (there is no separate `IOrchestator`
interface in this repository), passes the query unchanged to the selected
system, and uses the same `ES` or `EN` language for both calls.

Routing and system execution live in
`backend/src/utils/pipeline/func/handle_with_subsystem.py`; the `Pipeline` class
retains the public methods and cached dependencies. The frozen `PipelineResult`
and shared `SubsystemId` type live in
`backend/src/utils/pipeline/dataclass/models.py`.

```python
from systems.pipeline.Pipeline import Pipeline

pipeline = Pipeline()
result = pipeline.handle("Explain how to perform a squat", "EN")
```

`handle(query, language="EN")` returns the selected system's result unchanged:
plain text for Exercise Explainer and Past Routines Analyzer, or a
`RoutineMakerResult` for Routine Maker. A `no_system` selection returns the
localized no-match message without invoking a gym system.
`handle_with_subsystem(query, language="EN")` accepts the same arguments and
returns a frozen `PipelineResult` with `subsystem` (the orchestrator's selected
ID, including `no_system`) and `response` (the original text or
`RoutineMakerResult`). The endpoint uses this metadata-returning method.
`handle()` delegates to the same execution path and returns only `response`,
preserving its existing interface without routing twice.
Pass `session_id` and `user_id` for routine conversations. Routine Maker retains
collected parameters and draft JSON in the shared session cache, independently
of the last two conversational turns. `parameters` and a structured `RoutinePlan`
can optionally seed the Python interface. Pass `history` to supply workout
records to the analyzer; the pipeline does not fetch analyzer history.

The constructor accepts an existing `orchestrator` and optional
`routine_maker`, `exercise_explainer`, and `past_routines_analyzer` instances.
Omitted dependencies are created lazily on first use and reused; default
instances require the same Gemini configuration as the underlying systems.
Invalid queries/languages, unsupported subsystem IDs, and configuration or
provider errors propagate to the caller. The `POST /{id}/chat` endpoint wraps
this interface as documented above.

Run the pipeline tests from the repository root:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python -m unittest discover -s backend/tests -p test_pipeline.py -v
```

To run the live pipeline smoke test from the repository root:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_pipeline.py "Explain how to perform a squat" --language EN
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_pipeline.py "Explica cómo hacer una sentadilla" --language ES
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_pipeline.py "Analyze my progress" --language EN --history-file scripts_manual_func_tests/fixtures/past_routines_history.txt
```

The script requires `GEMINI_API_KEY` and optionally `LLM_MODEL` in `.env`.
It makes real routing and downstream Gemini calls, so API usage and quota apply.
It prints the full flow: input query/language, selected system, and every Gemini
call's model/settings, system prompt, user payload, response, and duration.
Routing retries appear as separate numbered API calls. The final section shows
the system's response (or routine status, parameters, and message), after a
total API call count. API keys are redacted from trace output; queries, history,
prompts, and responses are visible, so do not share logs containing private data.
Use `--parameters` with a JSON object and `--routine-file` with an existing
routine to test subsequent routine turns. Errors go to stderr and return exit
status 1.

## Exercise Explainer

`backend/src/systems/exercise_explainer/ExerciseExplainer.py` provides a
database-grounded Gemini workflow with prompts in
`backend/src/config/prompts/exercise_explainer/exercise_explainer.yaml`.
The first call extracts exercise names, including from memory for follow-ups,
translating Spanish names into English for catalog lookup. Each name is
fuzzy-matched against `dim_exercises` in `database/gym_app.db` using normalized
names, sequence similarity, token order, and subset matching. Exact normalized
matches take precedence; fuzzy matches require a score of at least 0.78 and
a lead of at least 0.08 over the next candidate.

Missing names return a text request for names. Unknown or ambiguous names
(including generic names with several equipment variants) return a text
clarification request identifying unresolved names and plausible candidates.
If any name is unresolved, no explanations are generated for that request:
the result never silently omits part of the requested list.

Matched rows are fetched read-only by ID using parameterized SQL. Results preserve
request order and deduplicate resolved IDs. Each exercise gets exactly one
separate explanation call using the original query, requested language, memory,
and its database context. The explainer uses **1 + N calls** for N unique matched
exercises, excluding the orchestrator's routing call. Clarifications use one call.

```python
from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer

explainer = ExerciseExplainer()
explanations = explainer.handle(
    "Explain Barbell Back Squat and Barbell Bench Press", language="EN"
)
if isinstance(explanations, list):
    print([exercise.model_dump() for exercise in explanations])
else:
    print(explanations)  # Clarification request.
```

`handle()` returns `list[ExerciseExplanation]` on success or text when
clarification is required, and accepts `EN` (default) or `ES`. Each exercise has:

- `id`, `name`, `description`, `instructions`, `icon_url`, `anatomy_diagram_url`:
  exact database values, without rewriting, trimming, or translation.
- `media_urls`: the two paths decoded from the database's JSON `media_url`
  string, preserving their exact values and order; SQL null remains JSON null.
- `llm_explanation`: the only generated field, grounded in the retrieved
  exercise and personalized to the query and previous explanation. The prompt
  requires an invitation to ask for further clarification.

The HTTP API serializes the models into a JSON list under `response`; the
pipeline also serializes this list into session memory for later follow-ups.
The backend serves only `database/images/` at `/database/images/`; stored paths
remain unchanged in JSON. Clients can resolve those paths against the backend
base URL. Frontend integration is not included in this backend-only change;
existing text-only clients must add support for the structured exercise list.

As with
Routine Maker, configure `GEMINI_API_KEY` and optionally `LLM_MODEL` in `.env`,
and put `backend/src` on `PYTHONPATH`. The constructor accepts an existing
`GeminiClient`, custom `prompt_path`, and keyword-only `database_path` for a
different catalog. Default database resolution is independent of the working
directory. Invalid input, malformed provider output or media JSON, database
failures, and provider errors propagate rather than producing fabricated data.
Calls using a real client consume API quota.

Run the mocked tests without API calls:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python -m unittest discover -s backend/tests -p test_exercise_explainer.py -v
```

## Past Routines Analyzer

`backend/src/systems/past_routines_analyzer/PastRoutinesAnalyzer.py` analyzes
caller-supplied workout history using the existing `GeminiClient`. Its prompts
are in `backend/src/config/prompts/past_routines_analyzer/past_routines_analyzer.yaml`.
The first call checks whether the query concerns past workouts and whether the
history supports an answer. Missing or insufficient history returns a request
for records; unrelated queries return a no-match message. These use one call.
Otherwise, the second call summarizes or compares the supplied records, with
instructions to explain missing data rather than invent progress or metrics.

The class delegates to `backend/src/utils/past_routines_analyzer/func/`, with one
utility function per file: `load_prompts.py`, `generate.py`, and `handle.py`.
The history-decision validation model lives in
`backend/src/utils/past_routines_analyzer/dataclass/models.py`; the class
interface and API call behavior are unchanged.

```python
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer

analyzer = PastRoutinesAnalyzer()
analysis = analyzer.handle(
    "Compare my squat progress",
    history=(
        "2026-10-01: Squat, 3 sets of 8 reps each at 60 kg.\n"
        "2026-10-08: Squat, 3 sets of 8 reps each at 65 kg."
    ),
    language="EN",
)
```

`handle()` returns plain text. `history` is optional text, including serialized
JSON, not a file path; use `None` when no records are available. Empty or non-text
history raises `ValueError`. `language` accepts `EN` (default) or `ES`.
The constructor accepts an existing client and a custom `prompt_path`.
Invalid input/output, configuration errors, and provider failures propagate.
There is no database access or automatic subsystem execution by the orchestrator.

To run the live functional test from the repository root, use the included
synthetic sample in `scripts_manual_func_tests/fixtures/past_routines_history.txt`:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_past_routines_analyzer.py "Compare my squat progress" --history-file scripts_manual_func_tests/fixtures/past_routines_history.txt --language EN
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_past_routines_analyzer.py "Analiza mi progreso" --history-file scripts_manual_func_tests/fixtures/past_routines_history.txt --language ES
```

The sample contains two squat sessions with the same sets and repetitions at
60 kg and 65 kg. For your own records, replace the `--history-file` path with
an existing UTF-8 file; relative paths are resolved from the working directory.

To test missing history, omit `--history-file`:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_past_routines_analyzer.py "Analyze my past workouts" --language EN
```

The query is optional and defaults to a workout summary and progress request.
The history file can be plain text or JSON; its contents are passed as text.
The script sends the query and history to Gemini using your root `.env`
configuration (`GEMINI_API_KEY`, optional `LLM_MODEL`); use only records you
intend to share with that provider. API usage and quota apply.
It prints the response or reports errors to stderr with exit status 1.

Run the mocked tests without API calls:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python -m unittest discover -s backend/tests -p test_past_routines_analyzer.py -v
```

## Routine Maker

`backend/src/systems/routinemaker/RoutineMaker.py` implements the Gemini-backed
routine workflow. Its four distinct system prompts are in
`backend/src/config/prompts/routinemaker/routinemaker.yaml`:

1. **Routing first:** classify `create`, `update_saved`, `update_draft`, `save`,
   or `no_match`, and extract current requirements/edit details. Pydantic validates
   the first model response against those allowed choices; invalid output gets
   up to three total attempts with validation feedback.
2. **Parameter collection:** ask only for missing requirements or edit details.
3. **Routine creation:** retrieve eligible exercises from SQLite, generate
   structured JSON, validate it, cache the draft, and ask for confirmation.
4. **Routine update:** load a user-owned saved routine or the current draft as
   context, collect the requested edit, and preview it for confirmation again.

The class delegates to `backend/src/utils/routinemaker/func/`, with one utility
function per file: `load_prompts.py`, `generate.py`, and `handle.py`.
`repository.py` handles catalog retrieval, ownership, validation and versioned saves.
Shared parameter, routing, and result models live in
`backend/src/utils/routinemaker/dataclass/models.py`. Parameter and result models remain importable
from `systems.routinemaker.RoutineMaker` for compatibility.

These are conditional stages, not four requests on every turn. A normal turn
makes one routing call followed by at most one collection/creation/update call;
text confirmation and unrelated input only need routing; the direct Save button
bypasses both the pipeline and Gemini entirely. Invalid generated JSON or
plans get up to three total generation attempts; provider failures propagate
without retrying them as validation errors. Requirements are `routine_type`
(`weider` or `ppl`), `days_per_week` (1-7), `hours_per_session` (positive, at most
24), and `level` (`beginner`, `intermediate`, or `advanced`). The routing prompt
normalizes English/Spanish terms, accepts PPPL as a PPL typo, and converts
session minutes to hours. Missing or ambiguous requirements are not guessed.
The result's `routine` is JSON with `name`, `summary`, `days`, and `recovery`.
Newly generated plans require a short localized `summary` (1-3 sentences, at
most 600 characters) explaining the split and rep targets without repeating the
exercise list. Older saved plans without a summary remain readable. Each day has
`day`, `day_type`, `info`, `duration_minutes`, and `exercises`. Each exercise has
`exercise_id`, its database `name`, `sets`, `reps`, `rest_seconds`, and `notes`.
Exercise IDs must exist in `dim_exercises` at or below the requested experience
level; exercise names are copied from SQLite, not trusted from model output.
Validation enforces the exact training-day count, consecutive day numbers,
no duplicate exercises within a day, and the per-session time limit.
These checks run in Pydantic with database catalog context, alongside JSON/schema
validation. Malformed JSON, invalid targets, missing summaries, and non-catalog
exercise IDs receive validation feedback for up to **three total generation
attempts**. Exhaustion raises the validation error without replacing the cached
preview or writing a routine. Saving revalidates against the current database.

```python
from systems.routinemaker.RoutineMaker import RoutineMaker

maker = RoutineMaker()
result = maker.handle(
    "Make me a PPL routine", session_id="user-1-chat", user_id=1, language="EN"
)
print(result.message)  # Questions for the remaining requirements.

result = maker.handle(
    "Three days a week, one hour per session, beginner",
    session_id="user-1-chat", user_id=1,
    language="EN",
)
print(result.routine)

result = maker.handle(
    "Yes, save it",
    session_id="user-1-chat", user_id=1,
    language="EN",
)
print(result.message)
```

Use the same session/user on follow-ups. State is cached in the session hash under
`routine_state:<user_id>`, separate from numeric conversation-turn fields.
The existing Redis client uses **fakeredis**: drafts are process-local and lost
on restart; this is not a durable external Redis deployment.
Routine Maker turns also keep the plan in a separate `routine` field in session
memory. It is a JSON object, not a string embedded in `system_response`:
`routine.days[]` contains each day's `day`, `day_type`, `info`,
`duration_minutes`, and `exercises[]`; exercises contain catalog `exercise_id`,
`name`, `sets`, `reps`, `rest_seconds`, and `notes`. No weight is generated.
`routine` is null when no plan exists yet; `system_response` contains only the
follow-up or confirmation message. Each turn stores its own snapshot, so later
edits do not mutate earlier routines. Routing preserves this structured memory.
Non-routine turns retain their existing storage format. Direct Save button
requests also append a routine turn, using an empty `user_query` for the button
action instead of inventing a user chat message.
Parameter updates merge with known values. Invalid/ambiguous replacements clear
the previous value and trigger a question rather than silently reusing it.
Explicitly starting a fresh routine discards the previous draft's requirements.

For exercise edits, collect `action` (`add`, `remove`, `replace`, `adjust`),
training `day`, and `exercise_id`; replacement needs `replacement_exercise_id`,
and adjustment needs `details`. The model receives catalog names/IDs to resolve
named exercises, but IDs remain internal: user-facing messages and generated
descriptions use names, never ask for or display database IDs. Ambiguous saved
routine selection lists names newest first and accepts names or relative recency
to distinguish versions. Missing details produce `needs_changes`; missing/ambiguous
saved-routine selection produces `needs_routine` only when there is no unique
current routine (or sole saved routine) to select automatically. Without an
explicit selection, update requests load the user's current `is_active = 1`
routine from SQLite. Parameter-only schedule
changes are also supported. Exercise edits preserve unaffected exercises and
their prescriptions. Beginning any edit revokes the previous preview's confirmation.

Statuses are `needs_parameters`, `needs_changes`, `needs_routine`,
`awaiting_confirmation`, `saved`, and `no_match`. Only `saved` writes a routine.
Confirmation saves the preview as a **new active version** in `dim_routines`;
the user's previous versions are deactivated in the same transaction, preserving
their contents. Other users' active routines are unaffected. The description stores
the plan JSON, parameters, source routine ID, and an idempotent draft ID.
`routine_id` identifies the newly saved version. Retrying a committed draft does
not create duplicates. Planned sets are not inserted into completed workout logs.

`RoutineMaker(client=existing_client, prompt_path=custom_yaml,
database_path=custom_database, state_store=shared_store)` supports dependency
injection. The default client reads the same Gemini
configuration as the orchestrator but uses an 8192-token output budget for longer
routine responses; injected clients retain their own settings. Prompt loading is
independent of the working directory. Invalid requests or model responses,
configuration errors, and API failures propagate without silent fallbacks.
`POST /{id}/chat` supplies the session ID and accepts numeric `user_id`.
Missing/unknown users and selecting a routine owned by another user return 422.
The frontend passes the selected profile ID, renders day/exercise JSON, and offers
a separate database-save confirmation button. Successful saves automatically
store the recommendation in the selected user's local My Routine view, without
an additional save action or leaving the chat. The editable workout log is preserved.
Local-storage errors are surfaced without undoing the successful database save.
The shared `RoutineMaker` HTML card renders the JSON directly in chat previews
and My Routine: a short explanation, split/day/duration metadata, accessible day
tabs, exercise tables (sets, reps, rest, notes), and recovery advice. Exercise
help buttons prepare a coach explanation request. No weights or routine IDs
are displayed, and a preview does not pretend to be a completed workout.
The frontend stores the saved recommendation as JSON rather than Markdown;
previously stored Markdown recommendations remain readable.

The button calls `POST /{id}/routine/save` directly with
`{"user_id": 1, "draft_id": "<preview draft_id>", "language": "EN"}`.
This endpoint needs no Gemini configuration, loads only the session/user's cached
draft, and returns the same `{"subsystem": "routine_maker", "response": ...}`
envelope. New and modified previews expose a `draft_id` and show the button;
beginning an edit revokes the previous confirmation. Stale or foreign-scope
draft IDs return 422. Repeated saves of the same confirmed draft return its
existing routine ID without creating duplicates or reactivating old versions.
Save errors remain visible and can be retried using the same button.
Both direct saves and chat-requested saves render a shared saved-routine
confirmation card with the routine name, without displaying its database ID or repeating the full
plan. No additional recommendation-save button is shown.

Run the mocked workflow tests without API calls:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python -m unittest discover -s backend/tests -p test_routine_maker.py -v
```

## Gemini text smoke test

`backend/src/utils/general/GeminiApiCall.py` provides the reusable `GeminiClient`
dataclass using the Gemini Developer API and a Google AI Studio API key.
The root `test_gemini.py` imports this client and provides the command-line
smoke test. The client uses `python-dotenv` to read
configuration, loads the model from `LLM_MODEL`, and defaults to the budget-focused
`gemini-2.5-flash-lite` model with a 256-token output limit.

Put your Google AI Studio key and model in the repository-root `.env` (which is ignored
by Git). The `.en.sample` file provides a template; copy its contents into
your `.env` and replace the placeholder key. Do not overwrite an existing
`.env` containing other settings.

```dotenv
GEMINI_API_KEY=your_ai_studio_api_key
LLM_MODEL=gemini-3.1-flash-lite
```

From the repository root:

```bash
uv sync --project backend --locked
uv run --project backend --locked python test_gemini.py
uv run --project backend --locked python test_gemini.py "Explain Python dataclasses in one sentence."
```

The client reads the repository-root `.env`, independently of the working
directory. Existing `GEMINI_API_KEY` and `LLM_MODEL` environment variables take
precedence over the file. Explicit `api_key` and `model` constructor arguments
take precedence over both; `--model` overrides the configured model for the CLI.
If `LLM_MODEL` is unset, the model defaults to `gemini-2.5-flash-lite`.
A configured empty model is rejected.
Running it makes a real API request and prints the model and response. Failures
print an error to stderr and exit with status 1. API quota and billing apply;
see [Google's pricing](https://ai.google.dev/gemini-api/docs/pricing).
Use `--model MODEL_ID` to select another available model.

If a request returns HTTP 404, the script prints Google's error response
(with the key redacted). A valid key does not guarantee access to a particular
model. List the models available to your key, then select a text-generation
model from that list:

```bash
uv run --project backend --locked python test_gemini.py --list-models
uv run --project backend --locked python test_gemini.py --model gemini-3.1-flash-lite
```

Listing models does not generate text. `gemini-3.1-flash-lite` is another
budget-focused option; use it only if it appears in your model list.

To call it from backend Python code (with `backend/src` on `PYTHONPATH`):

```python
from utils.general.GeminiApiCall import GeminiClient

client = GeminiClient()  # Reads GEMINI_API_KEY and LLM_MODEL from the environment or .env.
answer = client.generate("Say hello in Spanish.")
```

Run its mocked tests without an API key or API charges:

```bash
uv run --project backend --locked python -m unittest discover -s backend/tests -p test_gemini_client.py -v
```

## Git ignore rules

The root `.gitignore` excludes generated Python and Node.js artifacts, local
environment files, and OS/editor temporary files throughout the repository.
The frontend `.gitignore` also excludes frontend-local files and VS Code
settings, while keeping recommended extensions.

Keep dependency manifests, lockfiles, `.env.example` and `.env.*.example`
templates, and source directories such as `frontend/src/lib/` in version
control. Secrets and generated caches inside source directories remain ignored.