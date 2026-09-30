# Security Policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability involving credentials, authentication,
authorization, remote runners, private match data, or code execution.

Until a dedicated private reporting channel is configured, contact the repository
owner through GitHub without including an exploit, token, or private user data in a
public thread. A formal private vulnerability-reporting channel must be enabled before
the first public beta.

## Secret-handling rules

- Never commit API keys, OAuth tokens, cookies, passwords, subscription credentials,
  database URLs containing passwords, or generated secret files.
- Never place secrets in issue descriptions, pull requests, screenshots, test
  fixtures, model prompts, match events, telemetry, or exported games.
- Use `.env.example` for names and non-sensitive examples only.
- Treat logs and model transcripts as potentially sensitive.
- Revoke and rotate a credential immediately if it is exposed.

## Trust boundaries

- The API service is authoritative for authentication, clocks, match state, and
  authorization.
- The chess arbiter is authoritative for legality and game results.
- Provider responses, remote runners, MCP clients, browsers, and human clients are
  untrusted inputs.
- Stockfish and third-party agent code execute outside the API process with explicit
  resource and network limits.

## Supported versions

The project is pre-release. Only the current default branch receives security fixes.
