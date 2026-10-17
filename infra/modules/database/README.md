# Neon database

Reusable Neon project, dedicated application role/database, and GCP Secret
Manager connection-secret integration. Files follow `versions.tf`,
`variables.tf`, `main.tf`, and `outputs.tf`; GCP names use
`<app_name>-<environment>`, with the secret suffix `-database-url`.

## Demo configuration and costs

- Frankfurt (`aws-eu-central-1`), because Neon does not support Madrid.
- PostgreSQL 16 by default.
- History retention is explicitly set to 21,600 seconds (six hours), the maximum
  allowed by the target Free organization. The pinned provider otherwise sends
  its 86,400-second default, which Neon rejects on this plan.
- One default production branch and one read/write compute. No replicas or
  additional branches/endpoints are created.
- Project compute defaults are pinned to 0.25 CU. The Free plan enforces
  suspension after 300 seconds of inactivity; Terraform must not send a
  `suspend_timeout_seconds` override, even with the same value.
- The `primary_compute` block is deliberately left computed: the pinned provider
  can send an implicit timeout override when that block is configured. Check
  the returned primary compute in the Neon console after deployment: min/max
  0.25 CU and timeout 300 seconds. These defaults are for creation, not a
  mechanism to resize an already existing compute. Mock tests validate the
  configured project limits, not the actual compute returned by Neon's API.
- At the time of implementation, the Neon Free plan includes 100 CU-hours per
  project per month, equivalent to up to 400 active hours at 0.25 CU, subject
  to the other Free-plan limits.

**A compute configuration cannot select or enforce a billing plan.** Use a
Neon account/organization on the **Free** plan, do not upgrade it, and monitor
usage. Paid-plan usage can incur charges even with these limits. Secret Manager
and cross-cloud traffic have separate GCP pricing; this module cannot guarantee
a zero total cloud bill. Do not add database keepalive or readiness queries
that prevent scale-to-zero.

The database starts without application tables or data. Neon also provisions
its standard default database and administrative role with the project.
The dedicated app role owns the new database. API-created Neon roles can have
Neon administrative memberships; this is not a restricted SQL runtime role.
Introduce a separate least-privilege SQL login and migration owner when the
application schema is migrated. No SQL, SQLite migration, or data import is
executed here.

The explicitly requested `kislerdm/neon` provider is pinned to `0.18.0`.
Its repository is archived; active maintenance has moved to
`neondatabase/neon`. Migrating provider source/state is a separate, reviewed
change. Do not run provider upgrades automatically in CI.

## Authentication

The Neon provider reads `NEON_API_KEY` from the environment. Set the GitHub
repository Actions secret `NEON_API_KEY`; do not commit it or put it in
Terraform variables or logs. Use a key scoped to the intended Free organization
where available. Both plan and apply require it.

Set the non-secret repository Actions variable `NEON_ORG_ID` to the organization
ID beginning with `org-` from Neon Organization settings. The workflow passes
it as `TF_VAR_neon_org_id`, and the module sets `neon_project.org_id` explicitly.
The API key must have access to that organization. For local Terraform commands,
export `TF_VAR_neon_org_id` as well; Terraform does not load the app's local
environment file or its `NEON_ID_ORG` setting automatically.

For GCP, use the existing GitHub OIDC setup. Before first deployment, run
`bash infra/scripts/bootstrap-database-access.sh` from the repository root as
an authorized administrator. This creates the separate runtime account and
grants the deployer narrowly scoped secret-management access. It does not
grant the runtime account project-level permissions. Terraform grants that
account accessor access on this secret only.

## Invocation

The production root already contains:

```hcl
module "database" {
  source                          = "../../modules/database"
  project_id                      = var.project_id
  app_name                        = "orchestratorapp"
  environment                     = "prod"
  neon_org_id                     = var.neon_org_id
  neon_region_id                  = var.neon_region_id
  db_name                         = "orchestrator_app"
  db_user                         = "orchestrator_app"
  cloud_run_service_account_email = var.cloud_run_service_account_email
  secret_region                   = var.region
  common_labels                   = var.common_labels
}
```

The connection uses the provider's **pooled** hostname, URI-encoded credentials,
and `sslmode=require`. Secret replication stays in Madrid independently of the
Neon region. Replacing the project, database, or secret is blocked by
`prevent_destroy`; credential rotation creates a new secret version and
disables the previous version when Terraform retires it.

Names and identifiers are not credentials, so those inputs are not marked
sensitive. Passwords come from Neon's sensitive computed role attribute;
the URI output is explicitly sensitive.

## Future Cloud Run integration

There is no Cloud Run Terraform resource in this repository yet. When adding
one, use the **runtime** account and wire the module outputs as follows inside
the service (retain its existing image and other settings):

```hcl
resource "google_cloud_run_v2_service" "backend" {
  # Existing name, location, and other service settings go here.
  template {
    service_account = var.cloud_run_service_account_email

    containers {
      # Existing image and other container settings go here.
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = module.database.secret_id
            version = module.database.secret_version
          }
        }
      }
    }
  }

  depends_on = [module.database]
}
```

The module dependency ensures the secret version and IAM binding exist before
Cloud Run deploys. Pinning the secret version makes revisions reproducible.
If Cloud Run is implemented in a sibling module, pass both outputs into that
module and put `depends_on = [module.database]` on its invocation.

**The Python application still uses SQLite.** Injecting `DATABASE_URL` is not
enough to make it PostgreSQL-compatible; its driver, repository SQL, and
transaction behavior must be migrated later.

## State and credentials

The generated password and URI are stored in plaintext inside encrypted-at-rest
Terraform state and saved plan artifacts, even when marked `sensitive`.
Restrict state/artifact access and do not print `terraform output -raw` for
sensitive outputs or upload JSON plans. The production root deliberately
does not re-export the URI. The workflow retains its saved binary plan for
only one day and requires approval before apply.

## Tests

From the repository root:

```bash
terraform -chdir=infra/modules/database init -backend=false
terraform -chdir=infra/modules/database test
```

The tests mock both providers and do not create resources, connect to a
database, or require real credentials.
They verify the configured retention value and compute limits, but cannot
prove Neon API acceptance or validate an organization's current entitlements.

Sources:

- [Neon regions](https://neon.com/docs/introduction/regions)
- [Neon pricing](https://neon.com/pricing)
- [Pinned provider project schema](https://github.com/kislerdm/terraform-provider-neon/blob/v0.18.0/docs/resources/project.md)
- [Provider maintenance notice](https://github.com/kislerdm/terraform-provider-neon)
