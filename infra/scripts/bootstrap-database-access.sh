#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="basicrahgapp"
DEPLOYER="orchestratorapp@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_ID="orchestratorapp-runtime"
CREATE_ROLE="orchestratorSecretCreator"
MANAGE_ROLE="orchestratorDatabaseSecretManager"

SERVICE_ACCOUNTS="$(gcloud iam service-accounts list --project="${PROJECT_ID}" --format='value(email)')"
if ! grep -Fxq "${RUNTIME_ID}@${PROJECT_ID}.iam.gserviceaccount.com" <<< "${SERVICE_ACCOUNTS}"; then
  gcloud iam service-accounts create "${RUNTIME_ID}" --project="${PROJECT_ID}" \
    --display-name="OrchestratorApp Cloud Run runtime" --quiet
fi

ROLE_NAMES="$(gcloud iam roles list --project="${PROJECT_ID}" --format='value(name)')"
if ! grep -Fxq "projects/${PROJECT_ID}/roles/${CREATE_ROLE}" <<< "${ROLE_NAMES}"; then
  gcloud iam roles create "${CREATE_ROLE}" --project="${PROJECT_ID}" \
    --title="Orchestrator secret creation" \
    --description="Create the application database secret during Terraform deployment." \
    --permissions=secretmanager.secrets.create --stage=GA --quiet
fi

if ! grep -Fxq "projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" <<< "${ROLE_NAMES}"; then
  gcloud iam roles create "${MANAGE_ROLE}" --project="${PROJECT_ID}" \
    --title="Orchestrator database secret management" \
    --description="Manage the database connection secret, versions, and runtime access." \
    --permissions=secretmanager.secrets.get,secretmanager.secrets.update,secretmanager.secrets.getIamPolicy,secretmanager.secrets.setIamPolicy,secretmanager.versions.add,secretmanager.versions.get,secretmanager.versions.access,secretmanager.versions.disable,secretmanager.versions.enable \
    --stage=GA --quiet
else
  gcloud iam roles update "${MANAGE_ROLE}" --project="${PROJECT_ID}" \
    --add-permissions=secretmanager.versions.enable --quiet
fi

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOYER}" \
  --role="projects/${PROJECT_ID}/roles/${CREATE_ROLE}" \
  --condition=None --quiet

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOYER}" \
  --role="projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" \
  --condition="title=orchestrator-database-secret,description=Manage only the production database secret and its versions,expression=resource.name == 'projects/${PROJECT_ID}/secrets/orchestratorapp-prod-database-url' || resource.name.startsWith('projects/${PROJECT_ID}/secrets/orchestratorapp-prod-database-url/') || resource.name == 'projects/31049783945/secrets/orchestratorapp-prod-database-url' || resource.name.startsWith('projects/31049783945/secrets/orchestratorapp-prod-database-url/')" \
  --quiet
