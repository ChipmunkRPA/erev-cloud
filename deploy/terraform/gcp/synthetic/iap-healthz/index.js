'use strict';
// Cloud Run function entry point for the eRev strict-IAP health probe (lane P3c). Cloud Monitoring's
// synthetic monitor executes `SyntheticFunction` on its schedule; the Synthetics SDK turns a thrown
// error into a failed check and a normal return into a passed check, and records the execution in
// monitoring.googleapis.com/uptime_check/check_passed (resource type cloud_run_revision). All
// probe logic lives in probe.js, which is unit-tested offline with mocked fetch/clock.

const functions = require('@google-cloud/functions-framework');
const GcmSynthetics = require('@google-cloud/synthetics-sdk-api');
const { configFromEnv, runProbe } = require('./probe');

functions.http(
  'SyntheticFunction',
  GcmSynthetics.runSyntheticHandler(async () => {
    const config = configFromEnv(process.env);
    const result = await runProbe(config, { fetch: globalThis.fetch, now: Date.now });
    // One structured, credential-free line per execution for Cloud Logging (no header, no token).
    console.log(
      JSON.stringify({
        probe: 'erev-iap-healthz',
        ok: result.ok,
        class: result.class,
        status: result.status,
        latency_ms: result.latencyMs,
        target: config.targetUrl,
        message: result.message,
      })
    );
    if (!result.ok) {
      throw new Error(`${result.class}: ${result.message}`);
    }
  })
);
