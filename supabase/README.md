# Baseline migration

`migrations/20261010203734_baseline.sql` was created with
`supabase migration new baseline` (CLI 2.81.3). It contains only the application
schema; it does not install Supabase services, create an Auth account, or
configure Storage. Apply it once, atomically, with an owner/privileged connection.

The idempotent synthetic data seed is `app.persistence.seed` in the shared backend
package (`trialsync-seed`). Setup, fixture ownership, integrity/access constraints,
and disposable PostgreSQL validation are documented in
`backend/app/persistence/README.md`.

Migration ordering is tied to the PR stack: #14 (`pranav14`) depends on #13
(`pranav13`). Keep subsequent changes in their own issue PRs.
