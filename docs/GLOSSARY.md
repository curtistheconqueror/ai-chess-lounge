# Project Glossary

| Term | Meaning |
| --- | --- |
| Agent | A model-backed or programmatic chess participant operating through a player adapter. |
| Arbiter | The authoritative server-side chess domain component that validates and applies moves. |
| Assistance division | A disclosed class defining what position data and tools a competitor may use. |
| Competitor configuration | The complete provider, model, version, effort, prompt, tools, division, and time-control identity used for ratings. |
| Event | An immutable, ordered fact recorded during a match, such as a move, pause, retry, or takeover. |
| Exhibition | A watchable game that may use mixed settings and is not automatically eligible for a controlled leaderboard. |
| Lounge | The live spectator and participation experience. |
| Lab | The controlled experiment, tournament, measurement, and reporting experience. |
| Match | One governed contest containing one or more games under a declared configuration. |
| Move proposal | A player adapter's requested move and public strategy summary before server validation. |
| Player adapter | A provider-neutral implementation that converts a normalized move request into a move proposal. |
| Position version | A monotonically increasing number used to reject stale or duplicate move submissions. |
| Public strategy summary | A concise, intentionally generated plan/threat/confidence report; never private chain-of-thought. |
| Rated game | A game that satisfies one division's reproducibility and integrity requirements. |
| Remote runner | An independently operated process that receives authorized turns and returns signed move proposals. |
| Subscription bridge | A user-controlled local runner that calls an officially supported provider CLI/SDK using the user's subscription authentication. |
| UCI | Universal Chess Interface, the protocol used to communicate with Stockfish. |
