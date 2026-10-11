# Stage 3: decisions before hosted beta work

No hosting purchase, account/access change, migration or deployment is authorized
by this checklist. Tonight's route remains trusted private practice. Confirm:

- **Chess Supabase project:** exact project/organization, owner and existing
  read-only access. Recon Fleet Tracker access is separate. Verify the intended
  project's Auth, database revision and existing policy before proposing changes;
  use a secure configuration route, never credentials in chat or Git.
- **Cloudflare and domain:** intended account/domain and existing access, DNS/TLS
  ownership and proposed changes. Nothing has been verified or changed in this
  session. An OpenAI hosting address is excluded by Curtis's requirement.
- **Runtime host:** choose a persistent Python/WebSocket/Stockfish runtime,
  region, operator, backup/restore plan and approved monthly infrastructure cap.
  Prepare a concrete deployment/rollback review before purchasing or deploying.
- **Invites and seats:** retain the approved invite-only private beta. Identify
  the two participants through the approved flow; each controls their own seat
  and runner. Persist ownership and test third-user/wrong-seat denial, expiry,
  revocation, reconnect and restart before opening the hosted guard.
- **First provider and funding:** name the first supported provider/model and
  verify entitlement. BYO player-funded inference remains the default. Any
  owner-funded exception needs explicit approval and a numeric spend cap, with
  enforced budgets before calls. Human/Stockfish practice needs no paid model.

First restore the exact historical auth handoff into this environment; do not
reconstruct it from transcripts. Then integrate ownership, separate seat/runner
permissions and browser sign-in, run two-user isolation and physical-phone gates,
and present the exact release SHA, access/config diff, costs and rollback plan for
approval. Hosted startup stays blocked until these gates pass. No new migration,
live invitation, merge or deployment happened in this increment.
