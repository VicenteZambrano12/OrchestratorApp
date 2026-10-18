#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="basicrahgapp"
REGION="europe-southwest1"
SERVICE_NAME="orchestratorapp-prod"
DEPLOYER="orchestratorapp@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME="orchestratorapp-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
CREATE_ROLE="orchestratorCloudRunCreator"
MANAGE_ROLE="orchestratorCloudRunManager"

gcloud services enable run.googleapis.com --project="${PROJECT_ID}" --quiet

ROLE_NAMES="$(gcloud iam roles list --project="${PROJECT_ID}" --format='value(name)')"
for ROLE in "${CREATE_ROLE}" "${MANAGE_ROLE}"; do
  if [[ "${ROLE}" == "${CREATE_ROLE}" ]]; then
    PERMISSIONS="run.services.create,run.operations.get"
    TITLE="Orchestrator Cloud Run creation"
  else
    PERMISSIONS="run.services.get,run.services.update,run.services.getIamPolicy,run.services.setIamPolicy"
    TITLE="Orchestrator Cloud Run management"
  fi
  if grep -Fxq "projects/${PROJECT_ID}/roles/${ROLE}" <<< "${ROLE_NAMES}"; then
    gcloud iam roles update "${ROLE}" --project="${PROJECT_ID}" \
      --permissions="${PERMISSIONS}" --quiet
  else
    gcloud iam roles create "${ROLE}" --project="${PROJECT_ID}" \
      --title="${TITLE}" --permissions="${PERMISSIONS}" --stage=GA --quiet
  fi
done

# Creation is checked on the parent project before the service exists.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOYER}" \
  --role="projects/${PROJECT_ID}/roles/${CREATE_ROLE}" --condition=None --quiet

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOYER}" \
  --role="projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" \
  --condition="title=orchestrator-cloud-run,description=Manage only the production app service,expression=resource.name == 'projects/${PROJECT_ID}/locations/${REGION}/services/${SERVICE_NAME}' || resource.name == 'projects/31049783945/locations/${REGION}/services/${SERVICE_NAME}'" \
  --quiet

gcloud iam service-accounts add-iam-policy-binding "${RUNTIME}" \
  --project="${PROJECT_ID}" --member="serviceAccount:${DEPLOYER}" \
  --role=roles/iam.serviceAccountUser --condition=None --quiet
