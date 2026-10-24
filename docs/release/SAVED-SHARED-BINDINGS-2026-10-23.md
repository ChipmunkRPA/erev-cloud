# Saved shared return member bindings — October 23, 2026

Migration 0343 adds nullable portfolio_application_basis to estimate_version. Saving an
explicitly targeted shared RETURN_RATE draft captures current member contract IDs, immutable
external keys and original obligation IDs/keys. The API and editor show the saved member scope.
Clients cannot supply this server-owned field through draft create/update inputs. Unconfigured
and breakage drafts retain a null basis.

The version's existing database transition guard makes this field immutable after submission;
it remains editable only while DRAFT. Shared approval content includes a present saved basis,
while historical/local content without a basis preserves its previous hash shape. The loader
projects saved bindings into each computation group, supplies the native frozen member scope,
and restores the relevant portfolio input even after current membership rows have ended.
Unrelated groups' member names are not added to a group's frozen native member list.

Draft impact preview compares saved bindings with the current population before calculating.
Changed membership requires reviewing and saving the draft again; existing immutable estimate
definitions do not silently acquire targets for newly added members. Empty-population retirement
and changed target definitions still need an explicit application workflow.

Verification: migration upgrade and public draft save/read/preview succeed. The public workflow
checks retained bindings after member removal, refuses stale draft preview, reconstructs native
input from saved bindings, and exercises the real database immutable-state guard inside a
rolled-back savepoint. This guard check is not a completed public approval workflow. Thirty
focused loader/adapter/approval-basis cases and ten UI cases pass, with generated OpenAPI/client
types and scoped types/lint. Submission, approval events and formal recomputation remain open.
No deployment.
