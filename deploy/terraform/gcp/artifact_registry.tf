# Artifact Registry (05 DPL-38, DPL-05; G19 spec amendment on vulnerability scanning; BUILD_SPEC
# DEP-4 test_registry_and_monitoring). Docker format with IMMUTABLE tags: a tag can never be moved
# to another digest, and the services reference digests anyway (cloud_run.tf). Images are pushed
# by the authorised release pipeline (UI-5), never by the loop (DG-FORBID-07).

resource "google_artifact_registry_repository" "erev" {
  location      = var.region
  repository_id = var.artifact_registry_repository
  description   = "eRev images erev-api, erev-worker, erev-web (05 DPL-38); immutable tags; referenced by digest."
  format        = "DOCKER"
  labels        = local.labels

  docker_config {
    immutable_tags = true
  }

  dynamic "vulnerability_scanning_config" {
    for_each = var.vulnerability_scanning ? [1] : []
    content {
      enablement_config = "INHERITED"
    }
  }

  depends_on = [google_project_service.apis]
}

# Cloud Run pulls images with its service agent, not with the runtime service accounts.
resource "google_artifact_registry_repository_iam_member" "run_service_agent_reader" {
  location   = google_artifact_registry_repository.erev.location
  repository = google_artifact_registry_repository.erev.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${local.cloud_run_service_agent}"
}
