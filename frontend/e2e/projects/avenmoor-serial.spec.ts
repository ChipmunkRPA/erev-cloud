// Serial project `avenmoor-serial` (docs/02-PRD.md E2E-04; docs/dev-guide.md DG-E2E-03, DG-E2E-04):
// the journeys that share WLD-T-01, one worker, in E2E-04 order. Journey items import their
// `jnn()` modules and call them below; `EREV_E2E_UNTIL=J-nn` stops after that journey.
// BUILD_SPEC RPS-7a (SUP-RC-SMOKE, D-86): the release-candidate smoke journey. When DMO appends the E2E-04
// journeys, remove the `rcSmoke()` call or move it after J-22, because J-13.1 expects "Journal run not
// calculated 1" (sup-rc-smoke.md N-5).
import { rcSmoke } from "../journeys/rc-smoke.journey";
import { test } from "../support/fixtures";

test.describe.configure({ mode: "serial" });

rcSmoke();
