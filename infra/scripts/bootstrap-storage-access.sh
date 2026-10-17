#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="basicrahgapp"
SERVICE_ACCOUNT="orchestratorapp@${PROJECT_ID}.iam.gserviceaccount.com"
CREATE_ROLE="orchestratorBucketCreator"
MANAGE_ROLE="orchestratorBucketManager"

ROLE_NAMES="$(gcloud iam roles list --project="${PROJECT_ID}" --format='value(name)')"
if ! grep -Fxq "projects/${PROJECT_ID}/roles/${CREATE_ROLE}" <<< "${ROLE_NAMES}"; then
  gcloud iam roles create "${CREATE_ROLE}" --project="${PROJECT_ID}" \
    --title="Orchestrator bucket creation" \
    --description="Create the Terraform-managed application bucket." \
    --permissions=storage.buckets.create --stage=GA --quiet
fi

if ! grep -Fxq "projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" <<< "${ROLE_NAMES}"; then
  gcloud iam roles create "${MANAGE_ROLE}" --project="${PROJECT_ID}" \
    --title="Orchestrator bucket configuration" \
    --description="Read and update the Terraform-managed application bucket configuration." \
    --permissions=storage.buckets.get,storage.buckets.update --stage=GA --quiet
fi

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="projects/${PROJECT_ID}/roles/${CREATE_ROLE}" \
  --condition=None --quiet

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="projects/${PROJECT_ID}/roles/${MANAGE_ROLE}" \
  --condition="title=orchestrator-app-bucket,description=Manage only the Orchestrator application bucket,expression=resource.name == 'projects/_/buckets/orch_app_bucket'" \
  --quiet
