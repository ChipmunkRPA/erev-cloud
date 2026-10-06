# eRev Cloud hosted artifacts: Terraform and provider pins (docs/05-ARCHITECTURE.md §8.3 DPL-30;
# BUILD_SPEC DEP-3 test_versions). These files are artifacts only and are never applied
# (docs/00-GOAL.md §2 item 14 and §4; D-47). The exact provider version resolved by
# `terraform init -backend=false` is recorded in .terraform.lock.hcl next to this file.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    # Only google_project_service_identity (the Cloud SQL and IAP service agents, P3-R5 / P3-R1)
    # uses the beta provider: the GA provider 6.50.0 has no such resource. Same major pin.
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    # Database passwords (DPL-32) are generated in state, never written in code or tfvars.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    # The strict-IAP health probe's runner source (synthetic/iap-healthz) is zipped at plan time
    # for the Cloud Run function (P3c); no network and no build happen here.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}
