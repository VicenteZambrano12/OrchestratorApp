# Production infrastructure

Terraform manages the production application bucket and uses GitHub OIDC for
deployment. Only the `prod` environment exists. No application container, Neon
migration, Redis deployment, or bucket objects are included.

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

These identifiers are not private credentials, but using secrets keeps
compatibility with the example's `${{ secrets.* }}` references. Do not upload
a service-account JSON key.

**No GitHub repository variables are required.** The project, region, and bucket
name are declared in the production Terraform variables file. Artifact Registry
configuration is deferred until application container deployment.

Create the GitHub environment `prod`, restrict its deployment branch to `main`,
and configure reviewers if production approval is required. The workflow uses
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

Configure `VicenteZambrano12` as a required reviewer on `prod`, allow only `main`
deployments, and disable administrator bypass. Self-review must remain allowed
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
