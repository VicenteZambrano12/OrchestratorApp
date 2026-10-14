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
router from `backend/src/api/Endpoint/health.py`. Its initial endpoint is `GET /health`,
which returns HTTP 200 with `{"status": "ok"}`. Interactive API documentation is
available at `http://127.0.0.1:8000/docs`.

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
point and imports its routing utilities from `backend/src/utils/orch/`,
with one utility function per file named after that function.
Prompt loading, provider adaptation, request/selection validation, and no-match
messages live in those utility modules; the existing class interface is unchanged.
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

## Exercise Explainer

`backend/src/systems/exercise_explainer/ExerciseExplainer.py` provides a simple
two-call Gemini workflow with prompts in
`backend/src/config/prompts/exercise_explainer/exercise_explainer.yaml`.
The first call extracts an explicitly named exercise or list of exercises.
If none are named, it returns a request for names without a second call.
Otherwise, the second call explains each exercise's muscles, setup, execution,
breathing, common mistakes, and safety tips.

```python
from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer

explainer = ExerciseExplainer()
explanation = explainer.handle("Explain squats and bench press", language="EN")
```

`handle()` returns plain text and accepts `EN` (default) or `ES`. As with
Routine Maker, configure `GEMINI_API_KEY` and optionally `LLM_MODEL` in `.env`,
and put `backend/src` on `PYTHONPATH`. The constructor accepts an existing
`GeminiClient` and a custom `prompt_path`. Invalid input, malformed model output,
configuration errors, and provider failures propagate to the caller.
Orchestrator routing does not automatically execute this class.

To run the live functional test from the repository root:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_exercise_explainer.py "Explain how to perform a squat." --language EN
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_exercise_explainer.py "Explain squats and bench press." --language EN
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_exercise_explainer.py "Explica la sentadilla." --language ES
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_exercise_explainer.py "Explain an exercise." --language EN
```

The positional query is optional and defaults to a squat explanation.
`--language` defaults to `EN`. The last example tests missing exercise names
and should print a request for names rather than an explanation.
The script makes real Gemini requests using `.env`; API usage and quota apply.
It prints the response on success, or errors to stderr with exit status 1.

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

1. **Routing:** identify creation, follow-up answers, updates, or unrelated input
   and extract explicitly provided requirements into validated JSON.
2. **Parameter collection:** ask only for missing requirements.
3. **Routine creation:** generate a plain-text routine once all requirements exist.
4. **Routine update:** revise a supplied routine and summarize the changes.

The class delegates to `backend/src/utils/routinemaker/`, with one utility
function per file: `load_prompts.py`, `generate.py`, and `handle.py`.
Shared parameter and result models live in `models.py` and remain importable
from `systems.routinemaker.RoutineMaker` for compatibility.

These are conditional stages, not four requests on every turn. Routine requests
make one routing call followed by one collection, creation, or update call;
unrelated input makes only the routing call. Requirements are `routine_type`
(`weider` or `ppl`), `days_per_week` (1-7), `hours_per_session` (positive, at most
24), and `level` (`beginner`, `intermediate`, or `advanced`). The routing prompt
normalizes English/Spanish terms, accepts PPPL as a PPL typo, and converts
session minutes to hours. Missing or ambiguous requirements are not guessed.
Routine output is plain text for now, not a structured exercise schema.

```python
from systems.routinemaker.RoutineMaker import RoutineMaker

maker = RoutineMaker()
result = maker.handle("Make me a PPL routine", language="EN")
print(result.message)  # Questions for the remaining requirements.

result = maker.handle(
    "Three days a week, one hour per session, beginner",
    parameters=result.parameters,
    routine=result.routine,
    language="EN",
)
print(result.routine)

result = maker.handle(
    "Change it to four days a week",
    parameters=result.parameters,
    routine=result.routine,
    language="EN",
)
print(result.message)
```

Conversation state belongs to the caller: pass the previous result's
`parameters` and `routine` on each follow-up, keeping them separate per user.
Parameter updates merge with known values. Explicitly invalid or ambiguous
replacement requirements clear the previous value and trigger a question rather
than silently reusing it. Results expose `status`
(`needs_parameters`, `created`, `updated`, or `no_match`), validated `parameters`,
user-facing `message`, and `routine`. Collection and unrelated requests preserve
the existing routine. Updates require a non-empty existing routine; absent
routine state raises `ValueError`. `language` accepts `EN` and `ES`.

`RoutineMaker(client=existing_client, prompt_path=custom_yaml)` supports client
injection and alternate prompts. The default client reads the same Gemini
configuration as the orchestrator but uses a 4096-token output budget for longer
routine responses; injected clients retain their own settings. Prompt loading is
independent of the working directory. Invalid requests or model responses,
configuration errors, and API failures propagate without silent fallbacks.
No HTTP endpoint or automatic orchestrator dispatch is added.

Run the live Routine Maker smoke test from the repository root, using the same
Gemini configuration as the orchestrator:

```bash
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_routine_maker.py
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_routine_maker.py "Make me a Weider routine" --language ES
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_routine_maker.py "One hour per session, beginner" --parameters '{"routine_type":"ppl","days_per_week":3}'
PYTHONPATH=backend/src uv run --project backend --locked python scripts_manual_func_tests/test_routine_maker.py "Change to four days a week" --routine-file routine.txt --parameters '{"routine_type":"ppl","days_per_week":3,"hours_per_session":1,"level":"beginner"}'
```

The default query supplies all four requirements for routine creation. The script
prints the result status, collected parameters as JSON, and the routine or
follow-up message. For later turns, copy the printed JSON into `--parameters`;
for updates, save the routine text in a UTF-8 file and pass `--routine-file`.
Each invocation handles one turn and makes real API calls; usage and quota apply.
Errors go to stderr and return exit status 1; HTTP error bodies redact the API key.

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