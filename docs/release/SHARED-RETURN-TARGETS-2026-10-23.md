# Shared return target entry — October 23, 2026

The portfolio estimate definition form now accepts common target obligation keys, one per
line, for RETURN_RATE. Creation resolves each key against every current portfolio member
under the portfolio membership lock and retains the resulting original obligation IDs in
the immutable estimate definition. The estimate list shows the saved keys. Existing approval
content already includes these IDs, so targets form part of the reviewed basis.

Duplicate keys, a missing key on any member, an empty member population with explicit targets,
and explicit targets on BREAKAGE refuse atomically. An omitted target list still allows an
unconfigured definition; it is not an applicable shared estimate. Adding/removing members
after definition creation does not silently invent new target bindings. Common member keys
are the currently representable native shared-return scope; distinct member keys require
per-member application bindings.

This supersedes the target-entry gap in SHARED-VERSION-LOADER-2026-10-23.md. Approval submission,
impact preview, frozen application bindings and revenue recomputation remain open. No approval
or posting was enabled by this UI change, and no deployment was performed.

Verification: the real public workflow saves/reloads targets, refuses missing and duplicate
keys without advancing the parent ETag, and retains authorization checks. Nine portfolio UI
cases pass, including target entry through the creation request. OpenAPI/client types were
regenerated; frontend TypeScript/ESLint and scoped backend Ruff/mypy pass.
