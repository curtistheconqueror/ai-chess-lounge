# ADR 0005: Use a React/Vite client for the first standalone Lounge

- **Status:** Accepted
- **Date:** 2026-09-30
- **Owners:** CurtisTheConqueror / project contributors

## Context

The first release needs a highly interactive board, replay controls, live
WebSockets, and a standalone deployment without tying the product to any model
provider or ChatGPT surface. Server-side rendering is not required for the live
arena itself.

## Decision

Use React and TypeScript with Vite for the Stage 1 client. FastAPI serves the
production static build and owns all authoritative chess state.

## Consequences

- Contributors get a fast, conventional frontend development loop.
- One production container can serve both the static client and API.
- The application remains deployable to a separate public URL.
- If public editorial or SEO-heavy routes later justify server rendering, the
  team may add a separate presentation surface without moving match authority out
  of FastAPI.

## Alternatives considered

- Next.js: capable, but adds a second production server without a Stage 1 need.
- Server-rendered templates: simpler runtime, but weaker component and interaction
  ergonomics for the live board.
- Provider-hosted app surface: rejected because the Lounge must remain independent.

## Verification

The production build must compile to static assets, load through FastAPI, reconnect
to an active game, and pass TypeScript validation in CI.
