# Cloud SQL for PostgreSQL 17 (05 DPL-32, DPL-39, SAR-30, OPR-08, OPR-16, OPR-17, KEY-01, KEY-06;
# BUILD_SPEC DEP-3 test_cloud_sql). Private IP only, PITR with var.pitr_log_retention_days of
# transaction logs, 30 retained daily backups, CMEK when use_cmek, pgAudit flags, deletion
# protection. Role passwords are generated in state and written to Secret Manager; no password
# appears in code, tfvars or outputs (REQ-SEC-002).

locals {
  # 05 SAR-30 flags plus the connection ceiling the budget is measured against (§2.7) and the lock
  # table behind it. Lock budget (05 §2.7): PostgreSQL sizes its shared lock table at server start
  # as max_locks_per_transaction × (max_connections + max_prepared_transactions) slots for the
  # whole instance. A statement that reads a partitioned table without a value for the partition
  # column locks the parent, its partitioned indexes, every partition and every index of every
  # partition until its transaction ends: 1,092 relations for audit_event, 910 for schedule_line
  # and 1,092 for subledger_line, 3,094 together (180 monthly partitions and the default each;
  # one contract computation holds about 2,250). Rule:
  #   max_locks_per_transaction × (max_connections + max_prepared_transactions)
  #     >= floor(0.8 × max_connections) × 3,094 + 5,044 relations
  # 0.8 × max_connections is the session ceiling of the connection budget (db_connection_budget in
  # main.tf), so the requirement is 2,484 at 600 connections and 2,526 at 100. Without the flag the
  # instance runs on PostgreSQL's default of 64, and the tenth session that holds the footprint is
  # answered SQLSTATE 53200 (measured on PostgreSQL 17). `erev doctor` evaluates the rule on the
  # live catalogue as the production check lock-budget (05 SAR-40).
  db_flags = {
    "cloudsql.enable_pgaudit"        = "on"
    "pgaudit.log"                    = "ddl,role"
    "cloudsql.pgaudit_mask_literals" = "on"
    "log_connections"                = "on"
    "log_disconnections"             = "on"
    "max_connections"                = tostring(var.db_max_connections)
    "max_locks_per_transaction"      = tostring(var.db_max_locks_per_transaction)
  }
}

resource "google_sql_database_instance" "erev" {
  name                = "${local.name}-pg17-${local.env}"
  region              = var.region
  database_version    = "POSTGRES_17"
  encryption_key_name = var.use_cmek ? google_kms_crypto_key.cloudsql.id : null
  deletion_protection = true

  settings {
    tier              = var.db_tier
    edition           = var.db_edition
    availability_type = var.db_availability_type
    disk_type         = "PD_SSD"
    disk_autoresize   = true
    user_labels       = local.labels

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = var.pitr_log_retention_days
      start_time                     = "03:00"
      location                       = var.region

      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    dynamic "database_flags" {
      for_each = local.db_flags
      content {
        name  = database_flags.key
        value = database_flags.value
      }
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = false
      record_client_address   = false
    }

    maintenance_window {
      day          = 7
      hour         = 3
      update_track = "stable"
    }
  }

  lifecycle {
    precondition {
      condition     = var.environment != "production" || var.db_availability_type == "REGIONAL"
      error_message = "05 DPL-32: production requires availability_type = REGIONAL."
    }

    # 05 §2.7 hosted rule, BLOCKING (P3-R4): the plan fails when the worst-case connection budget
    # exceeds 80% of the max_connections flag set on this instance.
    precondition {
      condition     = local.db_connection_budget_ok
      error_message = "05 §2.7: max_db_connections_used (${local.max_db_connections_used}) exceeds 80% of db_max_connections (${local.db_connection_budget}). Lower instance maxima or pool sizes, or raise db_tier and db_max_connections."
    }
  }

  depends_on = [
    google_project_service.apis,
    google_service_networking_connection.psa,
    google_kms_crypto_key_iam_member.cloudsql_service_agent,
  ]
}

resource "google_sql_database" "erev" {
  name     = "erev"
  instance = google_sql_database_instance.erev.name
}

# Role passwords: 32 URL-safe characters so the connection URLs need no escaping. Cloud SQL creates
# both users as members of cloudsqlsuperuser; the compose init script's role attributes
# (NOSUPERUSER, NOBYPASSRLS, CREATE on the database for erev_owner only) are applied hosted by the
# first erev-migrate run or by RB-11 (question returned to the supervisor in the P3 record).
resource "random_password" "owner" {
  length      = 32
  special     = false
  min_lower   = 4
  min_upper   = 4
  min_numeric = 4
}

resource "random_password" "app" {
  length      = 32
  special     = false
  min_lower   = 4
  min_upper   = 4
  min_numeric = 4
}

resource "google_sql_user" "owner" {
  name     = "erev_owner"
  instance = google_sql_database_instance.erev.name
  password = random_password.owner.result
}

resource "google_sql_user" "app" {
  name     = "erev_app"
  instance = google_sql_database_instance.erev.name
  password = random_password.app.result
}

# Backup role, OFF by default (P6 ruling as re-ruled by D-95). D-95: specifying BYPASSRLS requires a superuser or a BYPASSRLS holder, and Cloud SQL customers have neither (cloudsqlsuperuser = CREATEROLE/CREATEDB/LOGIN; its membership does not inherit BYPASSRLS), so no documented path exists. Hosted production therefore has NO erev_backup role and NO pg_dump backup: its backup is the OPR-08 automated backup + PITR and its drill is OPR-12 (restore into the fresh instance named by var.restore_test_instance, UI-P6-2). When backup_user_enabled is
# set on a PostgreSQL where the attributes can be applied, Terraform creates the user and its URL
# secret and the first erev-migrate run applies NOSUPERUSER and the read-only grants (RB-11). No
# identity can read the URL until backup_url_secret_accessors names the P6 backup job.
resource "random_password" "backup" {
  count = var.backup_user_enabled ? 1 : 0

  length      = 32
  special     = false
  min_lower   = 4
  min_upper   = 4
  min_numeric = 4
}

resource "google_sql_user" "backup" {
  count = var.backup_user_enabled ? 1 : 0

  name     = var.backup_user_name
  instance = google_sql_database_instance.erev.name
  password = random_password.backup[0].result
}

resource "google_secret_manager_secret_version" "db_backup_url" {
  count = var.backup_user_enabled ? 1 : 0

  secret          = google_secret_manager_secret.static["db_backup_url"].id
  secret_data     = "postgresql+psycopg://${google_sql_user.backup[0].name}:${random_password.backup[0].result}@${google_sql_database_instance.erev.private_ip_address}:5432/${google_sql_database.erev.name}?sslmode=require"
  deletion_policy = "DISABLE"
}

resource "google_secret_manager_secret_iam_member" "backup_url_accessor" {
  for_each = var.backup_user_enabled ? toset(var.backup_url_secret_accessors) : toset([])

  project   = var.project_id
  secret_id = google_secret_manager_secret.static["db_backup_url"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}

# KEY-06: the database URLs (owner, app and, when enabled, backup) are the ONLY secret versions this
# module writes (05 DPL-32 requires it; DPL-36 keeps every other secret value out of Terraform).
# Their values exist in state only, which is why backend.tf.example demands a CMEK-encrypted GCS
# state bucket. The Cloud Run services pin these exact version numbers (cloud_run.tf), so a rotated
# URL is a new release.
resource "google_secret_manager_secret_version" "db_owner_url" {
  secret          = google_secret_manager_secret.static["db_owner_url"].id
  secret_data     = "postgresql+psycopg://${google_sql_user.owner.name}:${random_password.owner.result}@${google_sql_database_instance.erev.private_ip_address}:5432/${google_sql_database.erev.name}?sslmode=require"
  deletion_policy = "DISABLE"
}

resource "google_secret_manager_secret_version" "db_app_url" {
  secret          = google_secret_manager_secret.static["db_app_url"].id
  secret_data     = "postgresql+psycopg://${google_sql_user.app.name}:${random_password.app.result}@${google_sql_database_instance.erev.private_ip_address}:5432/${google_sql_database.erev.name}?sslmode=require"
  deletion_policy = "DISABLE"
}
