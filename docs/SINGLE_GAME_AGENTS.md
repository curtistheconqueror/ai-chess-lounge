# Single-game agents and human advice

## Local workflow

Choose White and Black independently. Use Human for the side you play; choose two
configured agents to spectate an autonomous game. Supported connection paths already
include direct OpenAI, Anthropic, Google and OpenRouter, operator-configured Ollama
or vLLM, and separately paired external SDK/MCP runners. Consumer subscriptions do
not generally provide API credentials; the existing specific Codex CLI bridge is a
separate authorization path. No new credential or account setup is performed here.

The browser requests one live game at a time. Finish or explicitly abort the live
game before New match. Start paused allows inspection or advice before any agent
dispatch. Current match configuration remains separate from next-match selectors.
The Model Lab/legacy API are unchanged; the creation check is not a global quota.

To advise an AI: pause on its turn, enable Suggestion mode, then drag a legal move
or tap its source and destination (including promotion choice). No piece moves.
The saved suggestion survives reload. Resume lets the AI consider it and choose
its own move. The AI may ignore it. Clear or replace while paused; seat changes,
reset and intervening lifecycle changes invalidate it. Stockfish/remote runner
suggestions are deliberately unavailable until a supported advice contract exists.
AI advice to human players continues through Ask an adviser and explicit confirmation.

## Compute and provider boundaries

Game compute usage lists accepted AI moves and adviser records. Known token and
cost subtotals show reporting coverage; unknown is never zero. Reasoning tokens may
already be included in output and are not added again. Retries/cancelled/failed
calls may be absent. These are observed subtotals, not complete billing or a hard
monetary budget. No model calls were made for acceptance testing in this stage.

The UI preserves adapter/model-specific effort menus and provider-default behavior
where there is no mapping. Existing allowlists are configuration, not verified
availability in the user's account. Live catalog discovery and model-specific
acceptance are still needed before claiming a particular paid model works today.
OpenRouter currently documents per-model `reasoning.supported_efforts`; do not
extend static effort menus to arbitrary models. References:

- https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
- https://openrouter.ai/docs/cookbook/administration/usage-accounting

## Verified capabilities and remaining gates

- Real Stockfish 19 works locally; target Elo 1320-3190 and unrestricted mode.
- Human play, autonomous independent fixture agents, human-to-AI suggestions,
  existing AI-to-human advice and provider payload normalization are locally tested.
- Local preview catalog reports direct providers unavailable (`credentials_missing`);
  no Ollama/vLLM models are configured. Thus actual frontier/local-model gameplay
  is not accepted yet. Select an existing authorized model path before a live trial;
  approve any paid request separately and define a bounded call/budget policy.
- Reverse advice for independently operated runners is deferred; their current
  signed play contract remains intact. No arbitrary custom code executes in the API.
- Hosted private play is blocked on exact a766a78 patch recovery, account/seat/runner
  ownership, browser sign-in, two-user isolation tests and approved external hosting.
  No hosted URL, Supabase write, migration, credential/access change or deployment.

See ADR 0035 and PICKUP for stage verification. Local one-process controls must not
be represented as multi-user authorization or a production spend limit.
