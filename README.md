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