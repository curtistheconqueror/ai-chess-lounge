# ADR 0017 — Local MCP facade over the runner protocol

Status: accepted for Stage 5C

## Decision

Use the official Python MCP SDK in a separately installable local stdio package.
One process owns one Stage 5A runner identity and uses the Stage 5B Python client
for claim, polling, heartbeat, binding, signing, and exact-payload retries. The
existing match manager remains the sole authority for legality, clocks and leases.

Pairing credentials enter through operator environment configuration, never tool
arguments or results. Watch and resource snapshots use a public-field allowlist
that excludes legal-move and engine assistance. Creation is an explicit startup
opt-in limited to human and paired remote seats. Paid-provider configuration stays
with the operator UI. Tool error messages suppress remote response bodies.

Only loopback API targets are accepted until ownership/visibility controls ship.
There is no unauthenticated public MCP HTTP endpoint. Host authorization, approved
subscription access, and unattended-loop scheduling stay outside this facade.

## Consequences

Any compatible stdio MCP host can use the same chess tools without browser control,
independent of provider. Resources expose current snapshot, FEN and PGN. The MCP
package is optional for API deployments but installed by development/CI test setup.
SDK versions and transitive additions are pinned alongside the API lock file.

Process restart loses runner credentials and needs a new pairing. Deliveries and
proposal cache are bounded to 32 entries. A receipt is distinct from a committed
move. Host-specific permissions may still require approvals; this integration does
not bypass them. Official subscription adapters remain Stage 5D; distributed
reconnect, revocation and quotas remain Stage 5E.

Tests exercise the actual MCP protocol with two independent clients and real match
persistence, plus a stdio subprocess. Typed resource context uses the SDK's bare
Context class to preserve private request state during Pydantic call validation.

## Read availability during an agent turn

The integration gate exposed an existing lock spanning the model's entire turn.
Snapshot reads now return a copy of the last locally committed projection when a
writer is busy. Writers already publish their private copy only after persistence.
This permits watch-before-submit without deadlock and avoids exposing uncommitted
moves. Revisions identify the snapshot; it can lag a concurrent writer. When no
writer is busy, reads retain the database reload and expiry path. Clock and result
adjudication remain with the writer and timeout task. Distributed read freshness
remains part of later multi-worker hardening.
