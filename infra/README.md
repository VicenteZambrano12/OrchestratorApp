# Production infrastructure

Terraform manages the production application bucket, empty Neon database, and
database connection secret, using GitHub OIDC for GCP deployment. Only the
`prod` environment exists. No application container, SQL schema, data migration,
Redis deployment, or bucket objects are included.

## Neon database

The reusable [`modules/database`](modules/database/README.md) module creates
the empty `orchestrator_app` database in Frankfurt (`aws-eu-central-1`), on the
default `prod` branch with one 0.25 CU compute that suspends after five minutes.
The suspension interval is enforced by Neon's Free plan, not explicitly set
through the API. Verify the created primary compute in the Neon console has
0.25 CU min/max and a 300-second timeout after applying.
Neon does not offer Madrid. The pooled PostgreSQL TLS connection URI is stored
in `orchestratorapp-prod-database-url` in Secret Manager, replicated in Madrid.
The module documentation includes all inputs, outputs, cost caveats, mock tests,
and the future Cloud Run wiring example.

Before deploying, set the **repository Actions secret `NEON_API_KEY`** using a
key for your Neon Free account/organization. The 0.25 CU limit does not select
or enforce the Free billing plan. GCP Secret Manager and cross-cloud traffic
may have separate costs. Do not paste the key into the repository or chat.

Also set the non-secret **repository Actions variable `NEON_ORG_ID`** to your
organization ID beginning with `org-` from Neon Organization settings.
The workflow maps it to `TF_VAR_neon_org_id` and passes it to `neon_project.org_id`.
The API key must belong to or have access to that organization. The local
`NEON_ID_ORG` setting is not read by Terraform or GitHub Actions automatically.
For local Terraform commands, export `TF_VAR_neon_org_id` explicitly.

If an apply partially succeeded before a Neon error, generate a fresh plan
after fixing configuration. Terraform will refresh and reuse the secret and
IAM resources already recorded in state. Do not reuse the old plan artifact
or delete those resources manually.

Run as an administrator:

```bash
bash infra/scripts/bootstrap-database-access.sh
```

This creates `orchestratorapp-runtime@basicrahgapp.iam.gserviceaccount.com` for
future Cloud Run use. Terraform grants it accessor access only on the database
secret. The separate `orchestratorapp` deployment account receives project-level
`secretmanager.secrets.create` (creation cannot be scoped to a nonexistent
secret) and secret-management permissions conditioned on this exact database
secret and its versions. It cannot delete the secret or read other app secrets
through these grants. The Secret Manager and IAM APIs must already be enabled.
New custom roles can take time to propagate before binding them.

Database credentials are present in Terraform state and binary plan artifacts.
`sensitive` prevents ordinary CLI display but does not remove them from state.
The database remains empty; the existing SQLite backend is not modified.

## Application bucket

The storage module follows the example's `modules/storage` layout and is wired
through `environments/prod/main.tf`. Production settings are in
`environments/prod/terraform.tfvars`:

- Project: `basicrahgapp`.
- Bucket: `orch_app_bucket`.
- Region: `europe-southwest1` (Madrid).
- Storage class: `STANDARD`.
- Uniform bucket-level access and public access prevention are enabled.
- The bucket is created empty: no objects, folders, or seed data are uploaded.
- `prevent_destroy = true` blocks Terraform destruction or replacement, and
  `force_destroy = false` prevents automatic removal of objects during deletion.

This is separate from the existing Terraform state bucket below.

### Manual image migration

After the bucket has been created, upload the contents of `database/images/`
under the `images/` prefix with the standalone standard-library Python script:

```bash
gcloud auth login
python3 scripts/migrate_images.py --dry-run
python3 scripts/migrate_images.py
```

The script uses your active `gcloud` identity; no service-account key or Python
package installation is needed. That identity needs object listing, reading,
creation, and replacement permissions on the app bucket (for example,
`roles/storage.objectUser` on this bucket). The Terraform CI account deliberately
does not have these object permissions; do not impersonate it for this migration.

Paths are resolved relative to the script, independently of the working directory.
For example, `database/images/anatomy/example.png` becomes
`gs://orch_app_bucket/images/anatomy/example.png`. Transfers are recursive and
checksum-based, skipping unchanged files and `.gitkeep` placeholders. Changed
destination objects are replaced; unrelated destination objects and all local
files are left untouched. Authentication and transfer errors exit nonzero.
The script does not create the bucket, change IAM, or make objects public.
It is manual only and is not part of the deployment workflow.

## Backend

The backend is defined in
[`environments/prod/backend.tf`](environments/prod/backend.tf):

- Bucket: `terraform_bucket_portfolio` (existing; not created or managed here).
- Prefix: `orchestrator_app`.
- Default workspace state: `gs://terraform_bucket_portfolio/orchestrator_app/default.tfstate`.
- Terraform also creates lock objects under this prefix while holding a lock.

GCS prefixes are not directories that need to be created. `terraform init`
configures access; state is persisted when Terraform writes state.

The backend must be configured in the root Terraform configuration, not in a
child module. The IAM bootstrap runs outside Terraform because access must
exist before Terraform can initialize its own backend.

## One-time IAM bootstrap

Run as an administrator already authorized to update the shared OIDC provider,
manage custom roles, and update this service account's and bucket's IAM policies:

```bash
bash infra/scripts/bootstrap-state-access.sh
```

New custom IAM roles can take time to propagate. If the first run reports that
the role does not exist in the bucket's hierarchy, wait and rerun the script.
Other failures must be investigated; the script stops rather than ignoring them.

The script adds bindings, preserving other applications' existing bindings:

1. Extend `github-provider` in `github-pool` to admit
   `VicenteZambrano12/OrchestratorApp` only on `refs/heads/main`, while retaining
   the existing provider condition.
2. Grant `roles/iam.workloadIdentityUser` on
   `orchestratorapp@basicrahgapp.iam.gserviceaccount.com` to the repository
   principal set:
   `principalSet://iam.googleapis.com/projects/31049783945/locations/global/workloadIdentityPools/github-pool/attribute.repository/VicenteZambrano12/OrchestratorApp`.
   The provider maps `attribute.repository` to `assertion.repository` and its
   condition restricts this repository to `main`. This avoids depending on the
   GitHub subject string, which varies with event and environment context.
3. Grant `roles/storage.objectAdmin` on the existing bucket with an IAM
   condition limiting object operations to `orchestrator_app/`, including
   Terraform state and lock objects.
4. Create the project custom role `orchestratorTerraformStateList`, containing
   only `storage.objects.list`, and bind it on this bucket, not on the project.

Object listing is bucket-wide: the account can see other objects' names and
listing metadata, but these grants do not let it read or modify their contents.
Terraform uses listing for workspace discovery. A separate bucket is required
if even other applications' object names must be hidden.

No Owner, Editor, project-wide Storage Admin, service-account key, or
Service Account Token Creator grant is needed. Do not use this Terraform state
identity as the application's Cloud Run runtime identity later.

### Bucket deployment permissions

Run as an administrator before the first bucket deployment:

```bash
bash infra/scripts/bootstrap-storage-access.sh
```

This grants the same GitHub Terraform service account:

| Custom role | Permissions | Scope |
| --- | --- | --- |
| `orchestratorBucketCreator` | `storage.buckets.create` | Project `basicrahgapp`; creation is checked on the project, so a bucket-name condition cannot constrain this permission. |
| `orchestratorBucketManager` | `storage.buckets.get`, `storage.buckets.update` | Project binding conditioned on `resource.name == 'projects/_/buckets/orch_app_bucket'`. |

The deployment account receives no app-object access, bucket deletion, or
bucket IAM modification permissions. Existing state-prefix access is unchanged.
New IAM roles and bindings can take time to propagate; if a new role is not yet
recognized, wait and rerun the script.

## GitHub configuration

Set these **repository Actions secrets**, retaining the supplied workflow's names:

| Secret | Value |
| --- | --- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/31049783945/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `GCP_TERRAFORM_SERVICE_ACCOUNT` | `orchestratorapp@basicrahgapp.iam.gserviceaccount.com` |
| `NEON_API_KEY` | Your Neon API key for the intended Free account/organization |

The two GCP identifiers are not private credentials, but using secrets keeps
compatibility with the example's `${{ secrets.* }}` references. `NEON_API_KEY`
is a private credential. Do not upload a service-account JSON key.

**The `NEON_ORG_ID` GitHub repository variable is required.** The GCP project, region, and bucket
name are declared in the production Terraform variables file. Artifact Registry
configuration is deferred until application container deployment.

Create the GitHub environment `prod`, allow the `main` and `refs/pull/*/merge`
branch patterns, and configure required reviewers. The workflow uses
`environment: prod` for environment protections; GCP trust uses the mapped
repository claim and the provider's branch restriction.

The workflow lives at
[`../.github/workflows/terraform-deploy.yml`](../.github/workflows/terraform-deploy.yml).
It runs only when a PR from `dev` is merged into `main`, retaining the example's
trigger and two-job saved-plan/apply sequence:

1. `build-and-plan` authenticates through OIDC without an environment approval,
   checks formatting, initializes and validates Terraform, lists workspaces,
   saves `tfplan`, shows it, and uploads the plan artifact.
2. `apply` depends on the successful plan job and uses the protected `prod`
   environment. It waits for approval, checks out the same commit, authenticates
   again, downloads the saved plan, initializes Terraform with the committed
   provider lock file, and applies that exact plan without replanning.

Configure `VicenteZambrano12` as a required reviewer on `prod`, allow `main` and
`refs/pull/*/merge` deployments, and disable administrator bypass. GitHub
environment branch protection can evaluate a `pull_request` deployment against
its PR merge ref even when the workflow runs after merging. Without the merge-ref
pattern, the apply job is rejected before it reaches the reviewer approval gate.
The workflow's `closed` trigger targeting `main` and merged-`dev` condition still
gate deployment; allowing the merge-ref pattern does not make unmerged PRs
eligible to apply this workflow. The GCP provider's `main` restriction is unchanged.
Self-review must remain allowed
if the repository owner both merges and approves the deployment.
An environment name alone does not enforce approval; its protection rules do.
Plan artifacts expire after one day, so approve within that window or rerun.
Concurrent production workflows are serialized without cancelling an active
deployment.

Both jobs need only `contents: read` and `id-token: write`. There are no Docker
builds, Artifact Registry operations, or function ZIP artifacts yet. The workflow
and infrastructure must be committed and merged through `dev` into `main`
before GitHub can create the bucket. Do not create it manually first.

## Validation

```bash
bash -n infra/scripts/bootstrap-state-access.sh
bash -n infra/scripts/bootstrap-storage-access.sh
bash -n infra/scripts/bootstrap-database-access.sh
terraform fmt -check -recursive infra
terraform -chdir=infra/environments/prod init -input=false -lockfile=readonly
terraform -chdir=infra/environments/prod validate
terraform -chdir=infra/environments/prod plan -input=false -lock-timeout=60s
```

Run initialization using the intended identity, not only an administrator, to
verify its access. IAM grants can take time to propagate. GitHub OIDC login
must ultimately be verified in a GitHub Actions job; local user credentials do
not test GitHub's token issuer, subject, or environment protections.

After the approved deployment, use an administrator's CLI credentials to confirm
the location and that the bucket contains zero objects; the deployment account
deliberately has no app-object listing access:

```bash
gcloud storage buckets describe gs://orch_app_bucket --format='value(location)'
gcloud storage ls --json gs://orch_app_bucket
```
