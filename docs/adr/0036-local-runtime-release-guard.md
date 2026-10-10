# ADR 0036: block accidental hosted startup of the local operator build

Status: protective local checkpoint; not a hosted-play release.

The current app has unauthenticated local operator routes. The exact historical
private-beta patch was recovered and hash-verified in the parent cloud task, but
the supported Library transfer helper cannot apply metadata on this Windows host.
Do not reconstruct that patch or remove its deny boundary to publish a preview.

## Decision

`LOUNGE_DEPLOYMENT` accepts only `local` or `hosted`; `LOUNGE_HOSTED_MODE` accepts
only `0` or `1`. Native development defaults to local. Any hosted request, conflicting
hosted/local flags, or unrecognized value refuses runtime startup in this build.
The guard runs before app lifespan, manager recovery, batch worker launch and
database initialization. It does not replace authentication or route authorization.

Container images default to `LOUNGE_DEPLOYMENT=hosted`, so an unchanged image fails
closed until hosted integration is reviewed. Local Compose explicitly opts into
local mode and retains its loopback port binding. The container command no longer
runs Alembic automatically. Existing local initialization remains compatible; an
operator must run any required migration separately under appropriate approval.
Explicit local mode is still a local-owner app: never expose it through a tunnel.

`DatabaseStore.validate_existing_schema` is a read-only integration building block:
read all Alembic heads and require exactly the expected revision, then verify every
required mapped table/column and any extra ownership columns provided by the caller.
It never creates/stamps schemas or unlocks startup. The future ownership migration
must supply its actual revision and requirements; passing today's schema does not
prove account isolation, grants, constraints or RLS. The recovered patch's startup
check must be semantically integrated with this method, not applied blindly.

The SPA previously returned a public repository README through an encoded parent
path. Public file paths now normalize both separator styles, reject parent paths,
absolute paths and drive/stream syntax, and resolve symlinks before requiring
containment under the public build directory. Index fallback and asset-root mount
also use the check. Individual asset paths retain Starlette's symlink containment.
No runtime process should permit untrusted modification of the build directory.

## Verification and remaining gates

Generated tests cover encoded separators, absolute/parent paths, file symlinks,
symlink asset roots, real Windows directory junctions, valid assets/permalinks,
invalid/missing hosted flags, zero startup work, multiple/missing schema heads,
missing tables/columns and read-only schema inspection. File-symlink cases require
a host that permits them; they run on Linux CI and may skip on Windows.

Private ownership, invitations, seat/runner authorization, session transport,
malformed Auth-response handling, two-user isolation and approved infrastructure
remain separate release gates. This checkpoint creates no accounts, credentials,
tunnels, production migrations, provider calls or deployment.
