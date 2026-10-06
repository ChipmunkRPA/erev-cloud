# Cloud Run (05 DPL-31, DPL-05, SAR-25, CMP-01 to CMP-03, CMP-09; hosted runtime contract of
# 2026-09-19 "Supported worker shapes and the selected design"; BUILD_SPEC DEP-4 test_cloud_run).
#
# Worker shape: the two workers stay Cloud Run SERVICES (DPL-31; contract recommendation), each
# running one supervised process that owns the Procrastinate loop and a small HTTP health listener
# on the injected PORT (lane P2 implements it). This module therefore declares:
#   - resources.cpu_idle = false and min 1 instance on both workers (instance-based billing;
#     background processing without requests);
#   - HTTP startup (/startupz: 5 s period, 2 s timeout, 36 failures = 180 s < Google's 240 s
#     bound) and liveness (/livez: 15 s period, 2 s timeout, 4 failures) probes instead of the
#     Docker exec health check;
#   - internal-only ingress: no public business endpoint;
#   - 100% traffic to the latest revision (no tagged revisions with revision-level minima).
# Images are referenced by DIGEST (DPL-05); secrets through secret_key_ref with pinned version
# NUMBERS (SAR-25); Direct VPC egress to the private Cloud SQL address (DPL-39).

locals {
  registry = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}"

  images = {
    api    = "${local.registry}/erev-api@${var.image_digests.api}"
    worker = "${local.registry}/erev-worker@${var.image_digests.worker}"
    web    = "${local.registry}/erev-web@${var.image_digests.web}"
  }

  # DG-KRN-JOB-11 queues: compute and close on the compute worker, the other six on the general one.
  compute_queues = ["compute", "close"]
  general_queues = ["imports", "outbox", "reports", "maintenance", "integrations", "ai"]

  # Plain environment shared by every Python workload (05 CFG-01, CFG-11, CFG-13, CFG-25, SAR-40).
  python_env = {
    EREV_ENV                     = "production"
    EREV_KEY_PROVIDER            = "gcp"
    EREV_GCP_PROJECT             = var.project_id
    EREV_GCP_KMS_KEK             = google_kms_crypto_key.app_kek.id
    EREV_GCP_SECRET_PREFIX       = var.secret_prefix
    EREV_LOG_FORMAT              = "json"
    EREV_LOG_LEVEL               = "INFO"
    EREV_PUBLIC_ORIGIN           = "https://${var.public_domain}"
    EREV_TRUSTED_PROXY_HOPS      = tostring(var.trusted_proxy_hops)
    EREV_EMAIL_BACKEND           = "smtp"
    EREV_SMTP_HOST               = var.smtp_host
    EREV_SMTP_PORT               = tostring(var.smtp_port)
    EREV_SMTP_USERNAME           = var.smtp_username
    EREV_SMTP_FROM               = var.smtp_from
    EREV_AI_PROVIDER             = var.ai_provider
    EREV_FILE_BACKEND            = "gcs"
    EREV_GCS_FILES_BUCKET        = google_storage_bucket.files.name
    EREV_GCS_AUDIT_DIGEST_BUCKET = google_storage_bucket.audit_digests.name
    # P3-R6: the pinned KEY-03 version reaches the runtime. GcpKeyProvider (lane P2) must read
    # projects/<project>/secrets/<prefix>security-hmac/versions/<this number> as the CURRENT signing
    # key, record key id `security-hmac:<this number>` on new security events, and verify historical
    # events with the version named in their stored hmac_key_id (rotation = add a version out of
    # band, pin it here, release). Never "latest".
    EREV_SECURITY_HMAC_SECRET_VERSION = var.secret_versions.security_hmac
  }

  # Secret-backed environment: name → {secret id, pinned version}. The database URLs pin the
  # version this module created; the others pin var.secret_versions (never "latest").
  runtime_secret_env = merge(
    {
      EREV_DB_APP_URL = {
        secret  = google_secret_manager_secret.static["db_app_url"].secret_id
        version = google_secret_manager_secret_version.db_app_url.version
      }
      EREV_SMTP_PASSWORD = {
        secret  = google_secret_manager_secret.static["smtp_password"].secret_id
        version = var.secret_versions.smtp_password
      }
    },
    var.ai_provider == "anthropic" ? {
      ANTHROPIC_API_KEY = {
        secret  = google_secret_manager_secret.static["anthropic_api_key"].secret_id
        version = var.secret_versions.anthropic_api_key
      }
    } : {},
  )

  api_secret_env = merge(local.runtime_secret_env, {
    EREV_METRICS_TOKEN = {
      secret  = google_secret_manager_secret.static["metrics_token"].secret_id
      version = var.secret_versions.metrics_token
    }
  })

  api_env = merge(local.python_env, {
    EREV_METRICS_ENABLED = "true"
  })

  worker_env = merge(local.python_env, {
    EREV_WORKER_CONCURRENCY = tostring(var.worker_concurrency)
  })

  # erev-migrate: the owner URL for the Alembic upgrade and the app URL for the DB-14 lint that
  # `erev migrate` runs as erev_app afterwards (DG-MK-migrate); both version-pinned.
  migrate_secret_env = {
    EREV_DB_OWNER_URL = {
      secret  = google_secret_manager_secret.static["db_owner_url"].secret_id
      version = google_secret_manager_secret_version.db_owner_url.version
    }
    EREV_DB_APP_URL = {
      secret  = google_secret_manager_secret.static["db_app_url"].secret_id
      version = google_secret_manager_secret_version.db_app_url.version
    }
  }

  # erev-tenant-provision (P3-R3): the app database URL only. `erev tenant create` writes the Tenant
  # Admin invitation as an outbox EMAIL row that the worker's SCH-03 relay sends, so the job needs no
  # SMTP credential (lane P2) and no AI key; the fake AI provider.
  provision_env = merge(local.python_env, {
    EREV_AI_PROVIDER = "fake"
  })

  provision_secret_env = {
    EREV_DB_APP_URL = {
      secret  = google_secret_manager_secret.static["db_app_url"].secret_id
      version = google_secret_manager_secret_version.db_app_url.version
    }
  }
}

# ---------------------------------------------------------------------------------------------
# erev-api (CMP-02): min 1, max 10, concurrency 40, 2 vCPU, 2 GiB, CPU allocated during requests
# only (cpu_idle = true), reachable only through the load balancer.
# ---------------------------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  labels   = local.labels
  # P3-R1: public invocation without an allUsers binding when var.invoker_iam_disabled (main.tf).
  invoker_iam_disabled = local.api_invoker_iam_disabled

  template {
    service_account                  = google_service_account.api.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = var.api_concurrency
    timeout                          = "300s"
    labels                           = local.labels

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run_egress.id
      }
    }

    containers {
      name  = "api"
      image = local.images.api

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.api_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.api_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret
              version = env.value.version
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 5
        timeout_seconds       = 2
        failure_threshold     = 36
        http_get {
          path = "/api/v1/readyz"
          port = 8080
        }
      }

      liveness_probe {
        period_seconds    = 15
        timeout_seconds   = 2
        failure_threshold = 4
        http_get {
          path = "/api/v1/healthz"
          port = 8080
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.accessor,
    google_artifact_registry_repository_iam_member.run_service_agent_reader,
  ]
}

# ---------------------------------------------------------------------------------------------
# erev-worker-compute (CMP-03): `erev worker --queues compute,close`; min 1, max 4; 4 vCPU,
# 8 GiB; CPU always allocated (cpu_idle = false); internal ingress only; HTTP probes against the
# worker health listener.
# ---------------------------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "worker_compute" {
  name     = "${local.name}-worker-compute"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  labels   = local.labels

  template {
    service_account       = google_service_account.worker.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    timeout               = "${var.worker_request_timeout_seconds}s"
    labels                = local.labels

    scaling {
      min_instance_count = var.worker_compute_min_instances
      max_instance_count = var.worker_compute_max_instances
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run_egress.id
      }
    }

    containers {
      name  = "worker-compute"
      image = local.images.worker
      # The image ENTRYPOINT is `erev`; args replace CMD ["worker"] (DPL-02): erev worker --queues compute,close
      args = ["worker", "--queues", join(",", local.compute_queues)]

      ports {
        container_port = var.worker_health_port
      }

      resources {
        limits = {
          cpu    = "4"
          memory = "8Gi"
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.worker_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.runtime_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret
              version = env.value.version
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 5
        timeout_seconds       = 2
        failure_threshold     = 36
        http_get {
          path = "/startupz"
          port = var.worker_health_port
        }
      }

      liveness_probe {
        period_seconds    = 15
        timeout_seconds   = 2
        failure_threshold = 4
        http_get {
          path = "/livez"
          port = var.worker_health_port
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.accessor,
    google_artifact_registry_repository_iam_member.run_service_agent_reader,
  ]
}

# ---------------------------------------------------------------------------------------------
# erev-worker-general (CMP-03): the other six queues; min 1, max 2; CPU always allocated.
# ---------------------------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "worker_general" {
  name     = "${local.name}-worker-general"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  labels   = local.labels

  template {
    service_account       = google_service_account.worker.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    timeout               = "${var.worker_request_timeout_seconds}s"
    labels                = local.labels

    scaling {
      min_instance_count = var.worker_general_min_instances
      max_instance_count = var.worker_general_max_instances
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run_egress.id
      }
    }

    containers {
      name  = "worker-general"
      image = local.images.worker
      args  = ["worker", "--queues", join(",", local.general_queues)]

      ports {
        container_port = var.worker_health_port
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = local.worker_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.runtime_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret
              version = env.value.version
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 5
        timeout_seconds       = 2
        failure_threshold     = 36
        http_get {
          path = "/startupz"
          port = var.worker_health_port
        }
      }

      liveness_probe {
        period_seconds    = 15
        timeout_seconds   = 2
        failure_threshold = 4
        http_get {
          path = "/livez"
          port = var.worker_health_port
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.accessor,
    google_artifact_registry_repository_iam_member.run_service_agent_reader,
  ]
}

# ---------------------------------------------------------------------------------------------
# erev-web (CMP-01, DPL-03, DPL-40): the SPA image behind the load balancer. The load balancer
# routes /api/* straight to erev-api, so nginx's proxy_pass to `api` is not exercised hosted; the
# api enforces the DPL-12 upload limits itself (05 §2.5 step 3).
# ---------------------------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "web" {
  name     = "${local.name}-web"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  labels   = local.labels
  # P3-R1: public invocation without an allUsers binding when var.invoker_iam_disabled (main.tf).
  invoker_iam_disabled = local.web_invoker_iam_disabled

  template {
    service_account                  = google_service_account.web.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 200
    timeout                          = "60s"
    labels                           = local.labels

    scaling {
      min_instance_count = var.web_min_instances
      max_instance_count = var.web_max_instances
    }

    containers {
      name  = "web"
      image = local.images.web

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = false
      }

      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 5
        timeout_seconds       = 2
        failure_threshold     = 12
        http_get {
          path = "/"
          port = 8080
        }
      }

      liveness_probe {
        period_seconds    = 30
        timeout_seconds   = 2
        failure_threshold = 3
        http_get {
          path = "/"
          port = 8080
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository_iam_member.run_service_agent_reader,
  ]
}

# ---------------------------------------------------------------------------------------------
# erev-migrate (CMP-09, DPL-31, OPR-16, RB-02): finite Cloud Run JOB running `erev migrate` as
# erev_owner. Executed by the operator before a release rollout; an on-demand backup precedes it.
# ---------------------------------------------------------------------------------------------

resource "google_cloud_run_v2_job" "migrate" {
  name     = "${local.name}-migrate"
  location = var.region
  labels   = local.labels

  template {
    task_count = 1
    labels     = local.labels

    template {
      service_account       = google_service_account.migrate.email
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
      timeout               = "${var.migrate_timeout_seconds}s"
      max_retries           = 0

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run_egress.id
        }
      }

      containers {
        name  = "migrate"
        image = local.images.api
        args  = ["migrate"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        dynamic "env" {
          for_each = local.python_env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.migrate_secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value.secret
                version = env.value.version
              }
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.accessor,
    google_artifact_registry_repository_iam_member.run_service_agent_reader,
  ]
}

# ---------------------------------------------------------------------------------------------
# erev-tenant-provision: the finite job that runs `erev tenant create …` under the provisioning
# identity (runtime contract: the only holder of secretmanager.secrets.create). The tenant
# arguments are supplied per execution with `--args`; the args here are the command prefix only.
# Lane P2 owns the idempotent provisioning workflow; this job is its hosted execution shape.
# ---------------------------------------------------------------------------------------------

resource "google_cloud_run_v2_job" "tenant_provision" {
  name     = "${local.name}-tenant-provision"
  location = var.region
  labels   = local.labels

  template {
    task_count = 1
    labels     = local.labels

    template {
      service_account       = google_service_account.provisioning.email
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
      timeout               = "600s"
      max_retries           = 0

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run_egress.id
        }
      }

      containers {
        name  = "tenant-provision"
        image = local.images.api
        args  = ["tenant", "create"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        dynamic "env" {
          for_each = local.provision_env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.provision_secret_env
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value.secret
                version = env.value.version
              }
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.accessor,
    google_project_iam_member.provisioning_creator,
    google_project_iam_member.provisioning_initializer,
    google_artifact_registry_repository_iam_member.run_service_agent_reader,
  ]
}
