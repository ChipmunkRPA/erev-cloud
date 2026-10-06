# Secret Manager (05 DPL-36, PRV-10, SAR-25, §6.5 KEY-03, KEY-05, KEY-06, KEY-10, KEY-11, KEY-12;
# BUILD_SPEC DEP-3 test_secrets_and_network). Every secret replicates to var.region only
# (user-managed replication: data residency, PRV-10). No secret VALUE is written here except the
# two KEY-06 database URLs generated in cloud_sql.tf (DPL-32); operators add the other versions out
# of band and pin their numbers in var.secret_versions.
#
# KEY-05 (per-tenant audit HMAC keys) is a template, <secret_prefix>audit-hmac-<tenant id>: the
# application creates those secrets at tenant provisioning through the erev-provisioning identity
# (main.tf), so no resource exists for them here.

locals {
  static_secrets = merge({
    db_owner_url = {
      id      = "${var.secret_prefix}db-owner-url"
      key     = "KEY-06"
      purpose = "erev_owner connection URL; erev-migrate only"
    }
    db_app_url = {
      id      = "${var.secret_prefix}db-app-url"
      key     = "KEY-06"
      purpose = "erev_app connection URL; api, worker, provisioning"
    }
    security_hmac = {
      id      = "${var.secret_prefix}security-hmac"
      key     = "KEY-03"
      purpose = "platform security_event chain HMAC key; versions are never destroyed (OPR-17)"
    }
    anthropic_api_key = {
      id      = "${var.secret_prefix}anthropic-api-key"
      key     = "KEY-10"
      purpose = "AI provider key; injected only when ai_provider = anthropic"
    }
    smtp_password = {
      id      = "${var.secret_prefix}smtp-password"
      key     = "KEY-11"
      purpose = "email relay credential"
    }
    metrics_token = {
      id      = "${var.secret_prefix}metrics-token"
      key     = "KEY-12"
      purpose = "/metrics bearer token"
    }
    },
    # Backup role URL (EREV_BACKUP_URL), created ONLY when backup_user_enabled (default false, D-95:
    # hosted production has no erev_backup); readers named by var.backup_url_secret_accessors only.
    var.backup_user_enabled ? {
      db_backup_url = {
        id      = "${var.secret_prefix}db-backup-url"
        key     = "KEY-06"
        purpose = "backup role connection URL; the P6 backup job identity only"
      }
    } : {},
  )
}

resource "google_secret_manager_secret" "static" {
  for_each = local.static_secrets

  project   = var.project_id
  secret_id = each.value.id
  labels    = merge(local.labels, { erev-key = lower(each.value.key) })

  annotations = {
    purpose = each.value.purpose
  }

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.apis]
}
