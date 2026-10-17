#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="basicrahgapp"
PROJECT_NUMBER="31049783945"
POOL_ID="github-pool"
PROVIDER_ID="github-provider"
REPOSITORY="VicenteZambrano12/OrchestratorApp"
SERVICE_ACCOUNT="orchestratorapp@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="terraform_bucket_portfolio"
LIST_ROLE="orchestratorTerraformStateList"

# Extend the shared provider without removing or weakening its existing trust.
CURRENT_CONDITION="$(gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
  --project="${PROJECT_ID}" --location=global \
  --workload-identity-pool="${POOL_ID}" --format='value(attributeCondition)')"
APP_CONDITION="(assertion.repository == '${REPOSITORY}' && assertion.ref == 'refs/heads/main')"
if [[ -z "${CURRENT_CONDITION}" ]]; then
  printf '%s\n' "Provider has no attribute condition; review shared trust before continuing." >&2
  exit 1
fi
if [[ "${CURRENT_CONDITION}" != *"${APP_CONDITION}"* ]]; then
  gcloud iam workload-identity-pools providers update-oidc "${PROVIDER_ID}" \
    --project="${PROJECT_ID}" --location=global \
    --workload-identity-pool="${POOL_ID}" \
    --attribute-condition="(${CURRENT_CONDITION}) || ${APP_CONDITION}"
fi

# Use the mapped repository claim; the provider enforces the main branch.
gcloud iam service-accounts add-iam-policy-binding "${SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPOSITORY}" \
  --condition=None --quiet

# GCS object listing cannot be restricted by an object-name IAM condition.
ROLE_NAMES="$(gcloud iam roles list --project="${PROJECT_ID}" --format='value(name)')"
if ! grep -Fxq "projects/${PROJECT_ID}/roles/${LIST_ROLE}" <<< "${ROLE_NAMES}"; then
  gcloud iam roles create "${LIST_ROLE}" --project="${PROJECT_ID}" \
    --title="Orchestrator Terraform state listing" \
    --description="List state workspace objects in the shared state bucket." \
    --permissions=storage.objects.list --stage=GA --quiet
  printf '%s\n' \
    "New IAM roles can take time to propagate. If the bucket binding fails, rerun this script after propagation." >&2
fi

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="projects/${PROJECT_ID}/roles/${LIST_ROLE}" \
  --condition=None --quiet

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role=roles/storage.objectAdmin \
  --condition="title=orchestrator-app-state,description=Access only Orchestrator Terraform state and lock objects,expression=resource.name.startsWith('projects/_/buckets/${BUCKET}/objects/orchestrator_app/')" \
  --quiet
