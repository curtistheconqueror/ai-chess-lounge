# Model adapter SDK surface

The initial Python SDK surface is implemented in
`services/api/lounge_api/adapters.py`. Every adapter implements:

- `list_models()`
- `capabilities(model)`
- `validate_configuration(player)`
- `choose_move(request, player)`
- `normalize_usage(usage)`
- `healthcheck()`

`ScriptedPlayerAdapter` is the deterministic reference implementation and
`StockfishPlayerAdapter` proves that an out-of-process engine uses the same contract.
`OpenAIResponsesAdapter` is the first hosted-provider implementation: it uses strict
structured output, `store: false`, normalized usage, and a server-owned
credential boundary. Provider packages register through `AdapterRegistry`; they must
not add provider branches to the chess domain.
Adding an adapter with public match settings also requires extending the typed,
fail-closed public-settings contract; credentials stay outside player configuration.
