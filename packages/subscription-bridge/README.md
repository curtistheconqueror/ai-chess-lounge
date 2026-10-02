# Local subscription bridge (Stage 5D)

This optional Python sidecar runs one authorized match through the **official
Codex CLI**, using that CLI's existing ChatGPT login. The standalone Lounge still
supports direct provider APIs, OpenRouter, local models, humans, Stockfish, and
independent MCP/HTTP runners. Installing this package does not require ChatGPT.
Only choosing this particular competitor requires an eligible CLI account.

## Setup (Linux or macOS)

From the repository root, with Python 3.12+:

```sh
python -m pip install -e packages/runner-sdk-python -e packages/subscription-bridge
```

Install/update the official Codex CLI using its official setup instructions, and
run `codex login` yourself on the bridge machine. Do not paste a provider token
into the Lounge. Choose a model actually available in the CLI's `/model` picker.
No API-key fallback is used. Provider policies, account limits, and organization
restrictions still apply.

```sh
lounge-subscription-bridge doctor --model YOUR_AVAILABLE_MODEL
```

Doctor checks installed command capabilities and reports only a sanitized login
method. It makes no inference request and does **not** prove model access, plan
tier, quota, or network availability. Unsupported older CLI versions fail closed.

In the Lounge's runner panel:

1. Choose **Subscription bridge (Codex CLI)**, enter the exact same model, and
   generate a pairing. Its public profile declares OpenAI, subscription access,
   provider-default effort, and the **open agentic** division.
2. Copy its pairing ID and run:

   ```sh
   lounge-subscription-bridge run --pairing-id PAIRING_UUID \
     --model YOUR_AVAILABLE_MODEL --authorize-next-match
   ```

3. Paste the **Lounge pairing code** at the hidden terminal prompt. This is a
   short-lived game-runner pairing code, not a provider credential.
4. When the terminal says Paired, refresh the Lounge runner list, select that
   seat, and start the match. Use a generous clock: CLI startup and thinking count
   toward the clock. Subscription pairings allow up to 120 seconds per move.

Repeat with a second pairing and terminal to play two subscription competitors.
They can select different available models. A single sidecar may answer only its
next match; it binds on the first delivery and refuses another match. There is no
approval prompt per move. The grant defaults to 300 moves / one hour, bounded by
`--max-turns` (1–1000) and `--max-seconds` (1–14400). These are local authorization
limits, not quota reservations. A new match requires a new pairing and launch.

`--base-url` defaults to `http://127.0.0.1:8000`; remote servers require HTTPS.
The currently local-owner Lounge API should not be exposed publicly without the
planned account/authentication stage. Windows support is deferred because child
process-tree cleanup currently uses POSIX process groups.

## Operation and disclosure

- Provider auth remains in the official CLI's credential store. The bridge never
  reads OAuth files, exchanges tokens, or sends provider credentials to the API.
- Runner credentials exist only in the parent process memory. The child receives
  board data, not pairing codes or runner credentials. Its environment excludes
  API keys, access tokens, and credential-bearing proxy configuration.
- Each turn starts a new ephemeral CLI session in a temporary directory with a
  read-only sandbox and no user configuration. ChatGPT login is forced; shell,
  unified execution, and web search are disabled by configuration. Required
  organization policies remain in effect; there is no bypass-sandbox flag.
- These controls are **not a certification of tool-free reasoning** across CLI
  versions or managed installations. Seats are restricted to open agentic, never
  mislabeled pure reasoning. The CLI's own auth and platform diagnostics remain
  under its control. Use a dedicated OS account for stronger local isolation.
- Only the final schema-constrained move and short public plan/threat are used.
  Private reasoning and raw CLI diagnostics are not logged or returned to users.
  Malformed output, auth errors, quota errors, or missed deadlines stop the
  bridge. There is no engine substitution or model retry.
- Exact duplicate deliveries reuse the proposal. Existing signed submission
  retries preserve their identity. The server decides legality and stale turns.
- Ctrl-C, timeout, and output overflow kill the child process group. Pause may
  invalidate an in-flight proposal; a stale submission ends the bridge rather
  than spending another model turn automatically. Revoke its runner session in
  the UI when finished. Server-enforced one-match grants/reconnect rules remain
  Stage 5E work; the current grant is enforced by this local sidecar.
- Native effort selection is deferred until model-specific CLI capabilities can
  be verified. The UI accurately declares provider default; it does not invent
  an API-to-CLI effort mapping. Usage/cost are unknown, not reported as zero.

## Provider coverage

Codex is the first implemented official CLI adapter, not an exclusivity decision.
The runner protocol and local orchestration are provider-neutral. Additional CLI
adapters need an officially allowed route, reliable auth/capability checks,
bounded structured output, and truthful assistance disclosure.

Claude subscription support is not advertised here: Anthropic documents official
CLI subscription login, but its third-party product restrictions require further
approval/clarification before this product offers that access. Use the existing
Anthropic API adapter or bring an independently authorized external runner.
Google consumer Gemini CLI subscription access was sunset; use the existing
Google API adapter. Do not extract or reuse either provider's OAuth tokens.

Official sources checked 2026-10-02:

- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/auth
- https://learn.chatgpt.com/docs/developer-commands?surface=cli
- https://learn.chatgpt.com/docs/config-file/config-reference
- https://learn.chatgpt.com/docs/models
- https://code.claude.com/docs/en/agent-sdk/overview
- https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals

Tests use an explicitly fake executable for reproducible full-game integration,
plus strict parsing, auth/environment boundaries, cancellation, bounded output,
one-match scope, and exact replay. Live account verification is recorded
separately in `docs/PICKUP.md`; fake CLI success is not live-provider evidence.
