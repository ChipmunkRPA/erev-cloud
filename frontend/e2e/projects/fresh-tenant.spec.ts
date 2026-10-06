// Fresh-tenant project (docs/02-PRD.md E2E-05; docs/dev-guide.md DG-E2E-03, DG-E2E-12): J-01, J-20,
// J-21 and J-23, each creating its own tenant with `createTenant` in its `beforeAll` and never touching
// WLD-T-01. Until a journey exists this project holds no test and scripts/e2e.sh skips it
// (PHASES BS-D-20).
export {};
