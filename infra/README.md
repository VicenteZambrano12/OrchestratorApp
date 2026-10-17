# Production Terraform state

This step configures only the GCS backend and GitHub OIDC access. It does not
deploy the application, migrate SQLite to Neon, or grant application deployment
permissions. Only the `prod` Terraform environment exists.

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
child module. No application, storage-bucket, or networking module is needed
for this step. The IAM bootstrap runs outside Terraform because access must
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

## GitHub configuration

Set these **repository Actions secrets**, retaining the supplied workflow's names:

| Secret | Value |
| --- | --- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/31049783945/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `GCP_TERRAFORM_SERVICE_ACCOUNT` | `orchestratorapp@basicrahgapp.iam.gserviceaccount.com` |

These identifiers are not private credentials, but using secrets keeps
compatibility with the example's `${{ secrets.* }}` references. Do not upload
a service-account JSON key.

**No GitHub repository variables are required for this backend-only step.**
`GCP_PROJECT_ID`, `GCP_REGION`, and `GCP_AR_REPOSITORY` belong to the later
application deployment setup, not GCS backend initialization.

Create the GitHub environment `prod`, restrict its deployment branch to `main`,
and configure reviewers if production approval is required. The workflow uses
`environment: prod` for environment protections; GCP trust uses the mapped
repository claim and the provider's branch restriction.

Each workflow job accessing state needs:

```yaml
permissions:
  contents: read
  id-token: write

steps:
  - uses: actions/checkout@v4
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
      service_account: ${{ secrets.GCP_TERRAFORM_SERVICE_ACCOUNT }}
  - uses: hashicorp/setup-terraform@v3
  - name: Terraform Init
    working-directory: infra/environments/prod
    run: terraform init -input=false
```

The source-change-filter job will additionally need `pull-requests: read`,
as in the example, when application deployment is implemented.

The workflow lives at
[`../.github/workflows/terraform-deploy.yml`](../.github/workflows/terraform-deploy.yml).
It runs only when a PR from `dev` is merged into `main`, retaining the example's
trigger. Its single backend-verification job uses `prod`, authenticates through
OIDC, checks formatting, initializes and validates Terraform, lists workspaces,
and runs a plan to exercise state access and locking. The plan is not applied.
Concurrent production state checks are serialized.

There are no Docker builds, Artifact Registry operations, function ZIP artifacts,
or apply jobs at this stage. Those app-specific deployment steps and the
example's saved-plan/apply sequence will be added when application deployment is
ready. The workflow needs the two repository secrets above but no repository
variables. It must be committed and merged into `main` before GitHub can run it.

## Validation

```bash
bash -n infra/scripts/bootstrap-state-access.sh
terraform -chdir=infra/environments/prod fmt -check
terraform -chdir=infra/environments/prod init -input=false
terraform -chdir=infra/environments/prod validate
```

Run initialization using the intended identity, not only an administrator, to
verify its access. IAM grants can take time to propagate. GitHub OIDC login
must ultimately be verified in a GitHub Actions job; local user credentials do
not test GitHub's token issuer, subject, or environment protections.
