# HTTPS load balancer (05 DPL-40, DPL-41, SAR-13; BUILD_SPEC DEP-4 test_load_balancer_https_only).
# Global external Application Load Balancer, serverless NEGs for erev-api and erev-web, Google-
# managed certificate, HTTPS proxy with the MODERN SSL policy (TLS >= 1.2), HTTP-to-HTTPS redirect,
# Cloud Armor on both backends, and an IAP block on both backend services controlled by
# var.enable_iap (default false). /api/* goes to the api; everything else to the web image.
# Strict-Transport-Security is added here, by the tier that terminates TLS (05 SAR-20 rev 1.53):
# every backend service of the HTTPS proxy sets it as a custom response header, and the HTTP
# listener only redirects. The api and the web image send none: behind this load balancer they
# speak to it, not to the browser.

locals {
  hsts_response_headers = ["Strict-Transport-Security: max-age=31536000; includeSubDomains"]
}

resource "google_compute_global_address" "lb" {
  name         = "${local.name}-lb-ip-${local.env}"
  ip_version   = "IPV4"
  address_type = "EXTERNAL"

  depends_on = [google_project_service.apis]
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.name}-api-neg-${local.env}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_region_network_endpoint_group" "web" {
  name                  = "${local.name}-web-neg-${local.env}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.web.name
  }
}

resource "google_compute_backend_service" "api" {
  name                    = "${local.name}-api-backend-${local.env}"
  load_balancing_scheme   = "EXTERNAL_MANAGED"
  protocol                = "HTTPS"
  enable_cdn              = false
  security_policy         = google_compute_security_policy.erev.id
  custom_response_headers = local.hsts_response_headers

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }

  dynamic "iap" {
    for_each = var.enable_iap ? [1] : []
    content {
      enabled = true
    }
  }
}

# P3-R1 healthz exemption: a second backend on the SAME api NEG without IAP, reached only by the
# /api/v1/healthz path rule below, so the public uptime check keeps probing the api while IAP is on.
# Cloud Armor still applies. Created only when enable_iap and iap_healthz_exemption are both true.
resource "google_compute_backend_service" "api_health" {
  count = var.enable_iap && var.iap_healthz_exemption ? 1 : 0

  name                    = "${local.name}-api-health-backend-${local.env}"
  load_balancing_scheme   = "EXTERNAL_MANAGED"
  protocol                = "HTTPS"
  enable_cdn              = false
  security_policy         = google_compute_security_policy.erev.id
  custom_response_headers = local.hsts_response_headers

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_backend_service" "web" {
  name                    = "${local.name}-web-backend-${local.env}"
  load_balancing_scheme   = "EXTERNAL_MANAGED"
  protocol                = "HTTPS"
  enable_cdn              = false
  security_policy         = google_compute_security_policy.erev.id
  custom_response_headers = local.hsts_response_headers

  backend {
    group = google_compute_region_network_endpoint_group.web.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }

  dynamic "iap" {
    for_each = var.enable_iap ? [1] : []
    content {
      enabled = true
    }
  }
}

# UI-7: who may pass IAP when it is on.
resource "google_iap_web_backend_service_iam_member" "api" {
  for_each = var.enable_iap ? toset(var.iap_allowed_principals) : toset([])

  project             = var.project_id
  web_backend_service = google_compute_backend_service.api.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

resource "google_iap_web_backend_service_iam_member" "web" {
  for_each = var.enable_iap ? toset(var.iap_allowed_principals) : toset([])

  project             = var.project_id
  web_backend_service = google_compute_backend_service.web.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

resource "google_compute_url_map" "https" {
  name            = "${local.name}-https-${local.env}"
  default_service = google_compute_backend_service.web.id

  host_rule {
    hosts        = [var.public_domain]
    path_matcher = "erev"
  }

  path_matcher {
    name            = "erev"
    default_service = google_compute_backend_service.web.id

    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.api.id
    }

    # Longest path match wins: exactly /api/v1/healthz bypasses IAP when the exemption is on.
    dynamic "path_rule" {
      for_each = var.enable_iap && var.iap_healthz_exemption ? [1] : []
      content {
        paths   = ["/api/v1/healthz"]
        service = google_compute_backend_service.api_health[0].id
      }
    }
  }
}

resource "google_compute_managed_ssl_certificate" "erev" {
  name = "${local.name}-cert-${local.env}"

  managed {
    domains = [var.public_domain]
  }
}

resource "google_compute_ssl_policy" "modern" {
  name            = "${local.name}-ssl-modern-${local.env}"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

resource "google_compute_target_https_proxy" "erev" {
  name             = "${local.name}-https-proxy-${local.env}"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.erev.id]
  ssl_policy       = google_compute_ssl_policy.modern.id
  quic_override    = "NONE"
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${local.name}-https-${local.env}"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.erev.id
  ip_address            = google_compute_global_address.lb.id
}

# HTTP exists only to redirect to HTTPS (HTTPS-only, REQ-SEC-001).
resource "google_compute_url_map" "http_redirect" {
  name = "${local.name}-http-redirect-${local.env}"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "${local.name}-http-proxy-${local.env}"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "${local.name}-http-${local.env}"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
  ip_address            = google_compute_global_address.lb.id
}
