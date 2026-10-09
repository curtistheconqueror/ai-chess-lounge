"""Public, bounded declarations and server-recorded comparison snapshots."""

import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdentityDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying_model: str | None = Field(default=None, min_length=1, max_length=160)
    underlying_provider: str | None = Field(default=None, min_length=1, max_length=120)
    model_family: str | None = Field(default=None, min_length=1, max_length=120)
    model_version: str | None = Field(default=None, min_length=1, max_length=160)
    access_route: str | None = Field(default=None, min_length=1, max_length=120)
    broker: str | None = Field(default=None, min_length=1, max_length=120)
    harness: str | None = Field(default=None, min_length=1, max_length=120)
    harness_version: str | None = Field(default=None, min_length=1, max_length=120)
    effort_raw: str | None = Field(default=None, min_length=1, max_length=512)
    listing_opt_in: bool = False
    listing_alias: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def listing_requires_consent(self):
        if any(isinstance(v, str) and not v.strip() for v in self.model_dump().values()):
            raise ValueError("Identity declarations cannot be whitespace-only.")
        if self.listing_alias and not self.listing_opt_in:
            raise ValueError("A comparison listing alias requires explicit opt-in.")
        return self


def evidence(value, source="unknown"):
    return {"value": value, "evidence": source if value is not None else "unknown"}


def snapshot(game, adapters=None):
    seats = {}
    engines = []
    for color in ("white", "black"):
        player = game.player_for_color(color)
        declared = player.comparison or IdentityDeclaration()
        provider = (
            evidence(declared.underlying_provider, "declared")
            if declared.underlying_provider
            else evidence(player.provider, "recorded_configuration")
            if player.adapter_id not in {"remote_runner", "openrouter", "ollama", "vllm"}
            else evidence(None)
        )
        raw = evidence(declared.effort_raw, "declared")
        mapped = None
        if adapters and player.effort is not None and player.adapter_id != "human":
            cap = adapters.get(player.adapter_id).capabilities(player.model)
            mapping = cap.get("provider_effort_map")
            mapped = mapping.get(player.effort) if isinstance(mapping, dict) else None
            if mapped is not None:
                raw = evidence(str(mapped), "recorded_adapter_mapping")
        route = {
            "direct_api": "api",
            "subscription_bridge": "subscription",
            "local": "local",
            "human": "human",
        }.get(player.connection_mode.value)
        seats[color] = {
            "kind": "human"
            if player.is_human
            else "engine"
            if player.adapter_id == "stockfish"
            else "model",
            "model": evidence(player.model, "recorded_configuration"),
            "underlying_model": evidence(declared.underlying_model, "declared"),
            "provider": provider,
            "provider_label": evidence(player.provider, "recorded_configuration"),
            "family": evidence(declared.model_family, "declared"),
            "version": evidence(declared.model_version, "declared"),
            "effort_raw": raw,
            "effort_declared": evidence(declared.effort_raw, "declared"),
            "effort_normalized": evidence(
                player.effort.value if mapped is not None else None, "recorded_adapter_mapping"
            ),
            "effort_setting": evidence(
                player.effort.value if player.effort else None, "recorded_configuration"
            ),
            "access": evidence(route, "recorded_connection_mode")
            if route
            else evidence(declared.access_route, "declared"),
            "execution": evidence(
                json.dumps(
                    {
                        k: player.settings[k]
                        for k in (
                            "move_timeout_ms",
                            "max_output_tokens",
                            "target_elo",
                            "move_time_ms",
                        )
                        if k in player.settings
                    },
                    sort_keys=True,
                ),
                "recorded_configuration",
            ),
            "connector": player.adapter_id,
            "connection_mode": player.connection_mode.value,
            "broker": evidence("OpenRouter", "recorded_configuration")
            if player.adapter_id == "openrouter"
            else evidence(declared.broker, "declared"),
            "harness": evidence(declared.harness, "declared"),
            "harness_version": evidence(declared.harness_version, "declared"),
            "division": player.division.value,
            "protocol": player.protocol_version,
            "listing_alias": declared.listing_alias if declared.listing_opt_in else None,
        }
        if player.adapter_id == "stockfish":
            summary = game.engine_summary
            seats[color]["version"] = evidence(
                summary.version if summary else None, "verified_runtime"
            )
            engines.append(
                {
                    "target_elo": player.settings.get("target_elo", game.stockfish_elo),
                    **({"full_strength": True} if player.settings.get("full_strength") else {}),
                    "move_time_ms": player.settings.get("move_time_ms", game.engine_move_time_ms),
                    "version": seats[color]["version"],
                }
            )
    return {
        "schema_version": "1.0",
        "seats": seats,
        "conditions": {
            "initial_time_ms": game.initial_time_ms,
            "increment_ms": game.increment_ms,
            "initial_fen": game.board.fen(),
            "divisions": sorted(s["division"] for s in seats.values()),
            "protocols": sorted(s["protocol"] for s in seats.values()),
            "opponent_kinds": sorted(s["kind"] for s in seats.values()),
            "engines": sorted(engines, key=lambda item: json.dumps(item, sort_keys=True)),
            "clock_information": "supplied",
            "effort_control": "fixed_configuration",
            "request_bounds": sorted(
                [
                    {
                        "adapter": game.player_for_color(c).adapter_id,
                        "max_output_tokens": game.player_for_color(c).settings.get(
                            "max_output_tokens"
                        ),
                        "move_timeout_ms": game.player_for_color(c).settings.get("move_timeout_ms"),
                    }
                    for c in ("white", "black")
                ],
                key=lambda item: str(item),
            ),
        },
    }


def outcome(game):
    return {
        "lifecycle": game.lifecycle.value,
        "status": game.status.value,
        "result": game.result,
        "takeover": bool(game.seat_history),
        "consultation": any(
            c.status == "played" or c.direction == "human_to_ai" for c in game.consultations
        ),
        "moves": len(game.moves),
        "observed_models": {
            c: sorted(
                {
                    m.player_metadata.provider_model
                    for m in game.moves
                    if m.player_metadata
                    and m.player_metadata.provider_model
                    and m.actor.endswith(":" + c)
                }
            )
            for c in ("white", "black")
        },
    }
