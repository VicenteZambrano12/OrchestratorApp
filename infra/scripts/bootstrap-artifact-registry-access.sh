#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="basicrahgapp"
REGION="europe-southwest1"
REPOSITORY_ID="orchestratorapp-repo"
DEPLOYER="orchestratorapp@${PROJECT_ID}.iam.gserviceaccount.com"
MANAGE_ROLE="orchestratorArtifactRegistryManager"
REPOSITORY_NAME="projects/${PROJECT_ID}/locations/${REGION}/repositories/${REPOSITORY_ID}"

REPOSITORIES="$(gcloud artifacts repositories list --project="${PROJECT_ID}" \
  --location="${REGION}" --format='value(name)')"
if ! grep -Fxq "${REPOSITORY_NAME}" <<< "${REPOSITORIES}"; then
  gcloud artifacts repositories create "${REPOSITORY_ID}" --project="${PROJECT_ID}" \
    --location="${REGION}" --repository-format=docker \
    --description="OrchestratorApp production Docker images managed by Terraform" --quiet
fi

FORMAT="$(gcloud artifacts repositories describe "${REPOSITORY_ID}" --project="${PROJECT_ID}" \
  --location="${REGION}" --format='value(format)')"
if [[ "${FORMAT}" != "DOCKER" ]]; then
  echo "Expected a Docker repository at ${REPOSITORY_NAME}." >&2
  exit 1
fi

ROLE_NAMES="$(gcloud iam roles list --project="${PROJECT_ID}" --format='value(name)')"
if ! grep -Fxq "projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" <<< "${ROLE_NAMES}"; then
  gcloud iam roles create "${MANAGE_ROLE}" --project="${PROJECT_ID}" \
    --title="Orchestrator image repository management" \
    --description="Read/update the application repository and delete old image versions." \
    --permissions=artifactregistry.repositories.get,artifactregistry.repositories.update,artifactregistry.versions.delete \
    --stage=GA --quiet
else
  gcloud iam roles update "${MANAGE_ROLE}" --project="${PROJECT_ID}" \
    --permissions=artifactregistry.repositories.get,artifactregistry.repositories.update,artifactregistry.versions.delete \
    --quiet
fi

gcloud artifacts repositories add-iam-policy-binding "${REPOSITORY_ID}" \
  --project="${PROJECT_ID}" --location="${REGION}" \
  --member="serviceAccount:${DEPLOYER}" --role=roles/artifactregistry.writer \
  --condition=None --quiet

gcloud artifacts repositories add-iam-policy-binding "${REPOSITORY_ID}" \
  --project="${PROJECT_ID}" --location="${REGION}" \
  --member="serviceAccount:${DEPLOYER}" --role="projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" \
  --condition=None --quiet
