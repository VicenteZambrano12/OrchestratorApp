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

## Production image builds and Artifact Registry

The original workflow ordering is preserved: a merged `dev` → `main` PR runs
source filtering, builds/pushes the image when needed, saves a Terraform plan,
then waits for `prod` approval before apply. Open, unmerged, or closed-without-
merge PRs do not publish images.

The dedicated repository is
`europe-southwest1-docker.pkg.dev/basicrahgapp/orchestratorapp-repo`; the image
package is `orchestratorapp`. It does not share cleanup policies with the
example's `portfolio-repo/basicragapp`.

Because the example builds **before** Terraform apply, bootstrap the empty
repository and CI access once as an administrator:

```bash
bash infra/scripts/bootstrap-artifact-registry-access.sh
```

Production Terraform imports that exact repository and manages its settings.
CI receives repository-scoped Artifact Registry Writer plus a custom role
limited to repository read/update and image-version deletion. It cannot create
or delete other repositories. No new GitHub secret is needed; the existing OIDC
deployer account is reused.

Repository variables must match production configuration:

| GitHub variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | `basicrahgapp` |
| `GCP_REGION` | `europe-southwest1` |
| `GCP_AR_REPOSITORY` | `orchestratorapp-repo` |

Application source, frontend, dependency manifests, Dockerfile, container-context
rules, or image-workflow changes trigger a build tagged with the merge commit
SHA. An already-published SHA is reused on a retry. Infrastructure-only PRs reuse
the newest image digest; an empty repository always triggers the initial build.
The selected immutable digest is passed as `app_container_image` into Terraform
and deployed to Cloud Run only after approval of the saved plan.

After publishing/resolving the image, CI deletes older versions of this exact
image package and verifies **at most two newest versions remain**. It never
deletes the selected image or images belonging to another package. Single-platform
`linux/amd64` builds disable separate provenance/SBOM manifests so those auxiliary
versions do not consume the two-image allowance. Artifact Registry also has
native KEEP-two / DELETE-old policies as a background safeguard; native cleanup
alone is asynchronous and does not enforce an immediate limit.

Retention is by image creation time, not tag update time. The first build can
only retain one version; subsequent distinct builds retain two. Older images
are intentionally unavailable for rollback. A failed plan does not remove the
newly pushed image, matching the example's build-before-approval workflow.

```bash
python3 -m unittest discover -s scripts -p test_registry_images.py -v
```

## Production Cloud Run deployment

`infra/modules/cloudrun` deploys the combined image as `orchestratorapp-prod`
in Madrid (`europe-southwest1`). The website is public; existing application
authentication continues to protect user features. The service runs as
`orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com`, not the CI deployer.
No VPC connector, Qdrant VM, or additional database is needed.

Configure deployment permissions on the existing service once as an administrator
(this also works when an earlier apply created the service but failed afterward):

```bash
bash infra/scripts/bootstrap-cloudrun-access.sh
```

CI receives a custom role for service creation and operation status reads at the
project level (creation is authorized on the parent project). Service read,
update, and IAM-policy access are bound directly on this app's service, not
through a project-level resource-name condition. The script requires the service
to exist and fails explicitly if it does not; it does not create a placeholder.
`roles/iam.serviceAccountUser` is bound on the runtime identity only. No service
deletion permission, broad Cloud Run Admin role, or new GitHub secrets are added.
The existing Cloud Run service agent handles image pulls from the same project.

Commit and merge a `dev` → `main` PR, inspect the saved Terraform plan, and approve
the `prod` environment. Terraform deploys the selected immutable image and routes
100% of traffic to the new revision. CI then checks service/revision readiness,
the configured image digest, `/api/health`, and the frontend root. Terraform's
`cloud_run_url` output contains the production URL. A failed post-deployment
check fails the workflow; it does not automatically roll back.

The JSON secret is mounted read-only at `/var/secrets/orch_app_secret.json`.
The module explicitly uses second-generation execution and mode `0444` so the
non-root container can read the root-owned secret volume. `app_secret_version`
defaults to the populated version `2`, not the empty Terraform seed version `1`.
After adding a new JSON version through the CLI, update `app_secret_version`
in `infra/environments/prod/terraform.tfvars` and deploy through the workflow.
The complete JSON never becomes a Terraform input or a printed workflow value.

Demo defaults are one CPU, 512 MiB memory, request-based CPU allocation,
minimum zero instances, and maximum one at service and revision level.
Startup/liveness probes use `/api/health`; they do not test database or Gemini
availability. Scale-to-zero reduces idle compute cost but is not a guarantee of
a zero bill. In-memory sessions can reset after idle shutdown, restart, or
deployment. A rollout can temporarily overlap instances; the limit is not a
replacement for a shared session store. Service deletion is protected.

## Combined frontend/backend container

The root [Dockerfile](Dockerfile) uses separate Node and Python dependency build
stages, then runs one non-root Python process. The final image contains the
frontend build and backend source/dependencies, but no Node tooling, local
database/images, environment files, or local GCP credentials. Build-context
inputs are restricted by [.dockerignore](.dockerignore).

```bash
docker build -t orchestratorapp:local .
```

The production entry point is `python -m server` with `backend/src` on
`PYTHONPATH`. It binds `0.0.0.0` on Cloud Run's `PORT` (default `8080`):

- `/` serves the built frontend.
- `/api/health` reaches the backend liveness endpoint.
- `/api/docs` and `/api/openapi.json` expose backend documentation.
- `/api/database/images/...` uses the existing image-serving configuration.

The frontend is built with `VITE_API_BASE_URL=/api`; no development proxy or
second server is needed. The existing backend-only development command and
unprefixed routes remain unchanged.

The image defaults to `MODE=CLOUD`. Supply the runtime environment variables
directly, or mount the populated `orch_app_secret` JSON as a **read-only file**
and set `APP_SECRETS_FILE` to its path. The Cloud Run deployment
mounts the secret at `/var/secrets/orch_app_secret.json` and sets:

```text
APP_SECRETS_FILE=/var/secrets/orch_app_secret.json
```

The entry point loads the JSON before importing the backend. Explicit process
environment values take precedence over JSON values. Invalid/missing configured
files fail startup without printing credentials. The application uses its runtime
service account for GCS; do not include a service-account key file in the image.
Building this Dockerfile alone does not deploy Cloud Run.

For a local Docker run with an existing, securely stored runtime JSON file
readable by container UID `10001`:

```bash
docker run --rm -p 8080:8080 \
  --mount type=bind,src=/secure/path/runtime.json,dst=/run/secrets/app.json,readonly \
  -e APP_SECRETS_FILE=/run/secrets/app.json \
  orchestratorapp:local
```

Local GCS access additionally requires ADC available to the container. Do not
pass the entire development environment file: it includes deployment-only
credentials and local-machine configuration.

The container intentionally uses one worker because chat/routine session state
currently lives in process-local fakeredis. Multiple workers or Cloud Run
instances do not share that state; deploying multiple instances requires a
shared store first.

## SQL client

The reusable synchronous client lives in `backend/src/sql/SQLClient.py`.
Add these settings to the repository-root `.env` (also shown in `.env.example`):

```dotenv
MODE=LOCAL
SQL_DATABASE_TYPE=sqlite
SQLITE_DATABASE_PATH=database/gym_app.db
```

Explicit constructor arguments override process environment variables, which
override `.env`, followed by the defaults above. Relative SQLite paths resolve
from the repository root, independently of the working directory. File databases
must already exist to avoid silently creating an empty database for a mistyped
path; `:memory:` is supported for temporary databases. Foreign keys are enabled.

With `backend/src` on the Python import path:

```python
from sql.SQLClient import SQLClient

with SQLClient() as db:
    users = db.fetch_all(
        "SELECT id, username FROM dim_users WHERE id = ?", (1,)
    )
    user = db.fetch_one(
        "SELECT id, username FROM dim_users WHERE username = :name",
        {"name": "Jamie Davis"},
    )
```

`execute(query, parameters)` and `executemany(query, parameter_sets)` return
affected row counts (`-1` when unknown). `fetch_one` returns a dictionary or
`None`; `fetch_all` returns a list of dictionaries. Use unique column names or
aliases when selecting joined tables. Bind values through parameters rather
than formatting them into SQL. The client accepts `?` positional and `:name`
named placeholders in either mode; it does not translate vendor-specific SQL.

A context manager connects, commits on success, rolls back on an exception, and
always closes. For manual lifecycle management, call `connect()`, then
`commit()` or `rollback()`, and finally `close()`. Closing without committing
discards pending writes. Use a separate client per request/thread and do not
nest context managers on the same client. Database and configuration errors
propagate to the caller.

### Neon / cloud mode

Set these repository-root `.env` settings to use the migrated Neon database:

```dotenv
MODE=CLOUD
DATABASE_URL=postgresql://USER:PASSWORD@HOST-pooler/DBNAME?sslmode=require
```

Use the existing **pooled** URI stored in Secret Manager secret
`orchestratorapp-prod-database-url`, not the Neon API key. For a local terminal
authenticated to GCP, inject it without printing or saving the credential:

```bash
export DATABASE_URL="$(gcloud secrets versions access latest \
  --secret=orchestratorapp-prod-database-url --project=basicrahgapp)"
```

On Cloud Run, inject this secret as the `DATABASE_URL` environment variable and
set `MODE=CLOUD`. The runtime service account already has access to that secret;
the application does not invoke `gcloud` or retrieve deployment API keys.

Cloud mode overrides the legacy `SQL_DATABASE_TYPE=sqlite` setting and routes
users, routines, workouts, exercise lookup, and history analysis through
PostgreSQL. Missing or non-TLS URLs fail explicitly, with no SQLite fallback.
Process environment variables override `.env`; explicit constructor types or
SQLite fixture paths take priority for isolated tests and local tooling.
`MODE=LOCAL` (the default) retains the SQLite configuration above. Unknown modes
or database types are rejected. PostgreSQL connections disable persistent
prepared statements for compatibility with Neon's pooler. Multi-statement
repository writes use a transaction-scoped PostgreSQL advisory lock, matching
SQLite's serialized write behavior. Returned SQL dates are ISO strings in both
providers; progress events identify the provider without exposing its URL.

The PostgreSQL integration suite uses a temporary local server and synthetic
data. Only the cloud connection destination is redirected; SQL and transactions
run against real PostgreSQL. It never connects to Neon:

```bash
uv run --python 3.12 --script scripts/test_cloud_database.py
```

Run the SQLite client tests without touching the application database:

```bash
PYTHONPATH=backend/src:backend/tests uv run --project backend --locked python -m unittest test_sql_client -v
```

## Application JSON secret

The reusable [secrets module](infra/modules/secrets) provisions
`orch_app_secret` in GCP Secret Manager, replicated in Madrid
(`europe-southwest1`). Its initial version contains exactly `{}`. No values from
the local environment file are copied, and the existing Neon connection secret
is unchanged.

The dedicated runtime service account receives `roles/secretmanager.secretAccessor`
on this secret only. Before the next production Terraform deployment, rerun the
existing bootstrap as an administrator to authorize the deployer to manage the
new secret:

```bash
bash infra/scripts/bootstrap-database-access.sh
```

Then use the existing plan / production approval / apply workflow. This adds no
new GitHub secret or variable.

Later, add populated JSON as a **new version** in Secret Manager rather than
putting credentials in Terraform or committing them to the repository. Terraform
manages only the empty seed version; later versions are not overwritten by
routine applies, and a disabled seed remains disabled. Use `latest` when reading
the populated secret, not the `app_secret_initial_version` output. The secret
contents are not yet loaded into the application automatically.

## Image storage

Images keep their existing `/database/images/...` URLs in both modes, so neither
database paths nor frontend code need rewriting:

- `MODE=LOCAL` serves the repository's `database/images` directory.
- `MODE=CLOUD` serves images through the backend from the private GCS bucket.
  `/database/images/media/example/0.jpg` reads
  `gs://orch_app_bucket/images/media/example/0.jpg`. There is no local fallback.

The optional `.env`/process setting `GCS_IMAGES_BUCKET` defaults to
`orch_app_bucket`. The backend uses **Application Default Credentials**, not a
Neon key or a signed/public bucket URL. On Cloud Run, use the existing
`orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com` runtime identity.
For local cloud-mode development, configure ADC once:

```bash
gcloud auth application-default login
```

If the Google SDK cannot determine the project, export
`GOOGLE_CLOUD_PROJECT=basicrahgapp` in the backend process environment.

The storage Terraform module grants that identity object-viewer access
conditioned on the `images/` prefix only. The condition does not grant bucket
listing, writes, deletion, or access to other prefixes; public access prevention
remains enforced. The deployer needs bucket IAM read/update permissions to manage
the new binding. Run the updated bootstrap once as an administrator, then use the
existing plan / production approval / apply workflow:

```bash
bash infra/scripts/bootstrap-storage-access.sh
```

These infrastructure changes must be applied before the Cloud Run runtime can
read images. Upload images using the previously supplied migration script if
the bucket is still empty; image requests do not upload anything.

Cloud image responses support GET, HEAD, ETag/Last-Modified revalidation, and
object cache-control metadata (defaulting to one hour of browser caching).
Missing images return 404. Credential, permission, and GCS service failures are
logged and return 503 rather than silently loading local files.

Run the isolated image-serving tests without GCP credentials:

```bash
PYTHONPATH=backend/src:backend/tests uv run --project backend --locked python -m unittest test_image_files -v
```

## Populate Neon from SQLite

After Terraform has created the Neon database and its connection-secret version,
run the standalone migration from the repository root:

```bash
uv run --script scripts/migrate_database.py --dry-run
uv run --script scripts/migrate_database.py
```

`uv` installs the script's isolated `psycopg` dependency; the backend dependencies
are unchanged. The default source is `database/gym_app.db`, resolved relative to
the script. Use `--source /absolute/path/to/copy.db` to import a different copy.
Pause local application writes while preparing and running the migration.

The dry run performs SQLite integrity/foreign-key checks and prints table counts.
It does not connect to Neon, read credentials, or write data.

For the real import, the script uses `DATABASE_URL` from the process environment.
If unset, it reads the latest `orchestratorapp-prod-database-url` secret in
`basicrahgapp` using your active `gcloud` identity. Authenticate with
`gcloud auth login` first; that identity needs access to the secret. No local
environment file is loaded automatically, and no API key is needed.
The PostgreSQL URI must specify `sslmode=require` or stronger.
Neither credentials nor row contents are printed.

This copies all four tables, including users, routines, workouts, and the exercise
catalog. It preserves IDs, nulls, integer flags, JSON-as-text, timestamps-as-text,
and image-path values. It creates PostgreSQL identity sequences, checks, foreign
keys, unique constraints, and the six application indexes. Each row is compared
with the source before commit; sequences preserve SQLite's autoincrement high-water
marks, including previously deleted IDs.

**The destination `public` schema must be empty.** The script refuses an existing
schema containing tables, sequences, or views; it never truncates or replaces data.
The import is transactional and rolls back on failure. A successful run must not
be repeated against the same database. Image uploads and cloud image-URL handling
are separate; this script does not modify their paths or grant public bucket access.
The application itself still needs its SQLite-to-PostgreSQL repository migration.

Tests use synthetic data and an isolated local PostgreSQL server, never Neon.
The bundled test server supports Python 3.10–3.12 (the migration script itself
does not have that upper-version restriction):

```bash
uv run --python 3.12 --script scripts/test_migrate_database.py
```

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

## User endpoints

`GET /users/{user_id}/days` returns exactly seven days, oldest first, including
today and the previous six days in UTC:

```json
[
  {"date": "2026-10-09", "day_of_week": "Friday", "has_routine": false},
  {"date": "2026-10-10", "day_of_week": "Saturday", "has_routine": true},
  {"date": "2026-10-11", "day_of_week": "Sunday", "has_routine": false},
  {"date": "2026-10-12", "day_of_week": "Monday", "has_routine": false},
  {"date": "2026-10-13", "day_of_week": "Tuesday", "has_routine": false},
  {"date": "2026-10-14", "day_of_week": "Wednesday", "has_routine": true},
  {"date": "2026-10-15", "day_of_week": "Thursday", "has_routine": false}
]
```

`has_routine` means the URL user logged a workout that day, not merely saved a
routine plan. Template sets (`training_id IS NULL`) are excluded. Multiple sets
or sessions on one day still produce one entry. Users without workouts receive
seven false flags. Unknown users return 404; invalid user IDs return 422.
This endpoint is read-only and does not require AI calls.

User endpoints each have their own router module in `backend/src/api/Endpoint/`:
`users.py` handles `GET /users`, `register_user.py` handles `POST /users`, and
`active_routine.py` handles `GET /users/{user_id}/routine`, and `set_routine.py`
handles `PUT /users/{user_id}/routine`. Shared user models,
SQLite persistence, and the user repository dependency live in `backend/src/api/user_deps.py`.

To set a user's current routine, send the complete routine JSON (`name`, `summary`,
`days`, and `recovery`) directly as the PUT body, using the same format returned
by GET. The endpoint returns HTTP 200 with the saved routine, normalizing exercise
names from the catalog. It saves a new version and marks all of that user's
previous routines inactive in one transaction, without changing other users'
routines or requiring a chat session. Previous versions remain available.
Days must be numbered consecutively from 1, exercises must exist in the catalog,
and each exercise may appear only once per day. Invalid input returns 422 and
unknown users return 404 without changing the active routine. The stored
parameters derive the day count and longest session duration from the plan;
the split and experience level remain unspecified.

The frontend uses this PUT endpoint for both the preview's Save button and
explicit chat confirmations. It sends `client_saves_routine: true` with chat
requests so confirmations return `save_requested` rather than saving twice.
The subsequent PUT includes `session_id`, `draft_id`, and `language` query
parameters, verifies the full body matches the cached preview, preserves the
preview's original parameters, and updates chat state and memory. Retrying the
same draft does not create a duplicate or reactivate an older version. Stale or
mismatched previews return 422. Chat clients that omit the flag keep the existing
server-side save behavior.

```bash
curl -X PUT http://127.0.0.1:8000/users/1/routine \
  -H "Content-Type: application/json" \
  --data-binary @routine.json
```

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