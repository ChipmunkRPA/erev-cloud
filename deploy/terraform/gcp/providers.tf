# Provider configuration (05 DPL-30). No credentials, access tokens or impersonation settings live
# here or in any tfvars file: an authorised operator supplies Application Default Credentials at the
# moment a plan is run, which the loop never does (DG-FORBID-07; 00-GOAL §4). Validation
# (`terraform validate`) needs no credentials and performs no API call.

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
  default_labels        = local.labels
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
  default_labels        = local.labels
}
