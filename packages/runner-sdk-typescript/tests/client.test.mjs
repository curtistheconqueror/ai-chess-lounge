import assert from "node:assert/strict";
import test from "node:test";

import {
  RunnerClient,
  canonicalJson,
  proposalFor,
  proposalSignature,
} from "../dist/index.js";

const signingKey = "c3RhZ2U1Yi1jb250cmFjdC1rZXktMzItYnl0ZXMhISE";
const deliveryPayload = {
  delivery_id: "061b82bc-902c-449a-a957-f41c8c55ea29",
  expires_at: "2026-10-02T12:00:30+00:00",
  request: {
    schema_version: "1.0",
    request_id: "request-1",
    match_id: "match-1",
    position_version: 7,
    color: "black",
    fen: "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
    moves_uci: ["e2e4", "e7e5"],
    pgn: "1. e4 e5",
    legal_moves: ["g1f3", "f1c4"],
    remaining_ms: 59000,
    move_deadline_ms: 30000,
    division: "legal_assist",
    public_summary_required: true,
  },
};
const credentialsPayload = {
  session_id: "a59ca4a6-3837-466a-b6f0-bd6459c8bfc4",
  runner_token: "lounge_rs_a59ca4a6-3837-466a-b6f0-bd6459c8bfc4.secret",
  signing_key: signingKey,
  permissions: ["turn:read", "move:submit", "heartbeat"],
  expires_at: "2026-10-02T16:00:00+00:00",
  player: { player_id: "player-1", display_name: "Sample bot" },
  websocket_path: "/ws/runners",
  next_turn_path: "/api/runner-sessions/turns/next",
  proposal_path_template: "/api/runner-sessions/turns/{delivery_id}/proposal",
  heartbeat_path: "/api/runner-sessions/heartbeat",
};

test("canonical signature matches the Python contract with Unicode", async () => {
  const proposal = proposalFor(deliveryPayload, {
    move: "g1f3",
    plan: "Développer — then castle.",
    threat: "Black may play …Nc6.",
    confidence: 73,
  });
  assert.equal(
    await proposalSignature(
      signingKey,
      deliveryPayload.delivery_id,
      "delivery:061b82bc",
      proposal,
    ),
    "0c366b4cf2b8386b927598a36690bd3252db2209fc653dad6d91bd98bf607272",
  );
  assert.match(canonicalJson(proposal), /D\\u00e9velopper/);

  const costProposal = proposalFor(deliveryPayload, {
    move: "g1f3",
    usage: {
      input_tokens: 4,
      output_tokens: 2,
      reasoning_tokens: 1,
      estimated_cost_usd: 1,
    },
  });
  assert.equal(
    await proposalSignature(
      signingKey,
      deliveryPayload.delivery_id,
      "delivery:061b82bc",
      costProposal,
    ),
    "0a8ce3185d29a1495b9b60f72e7ca80af0d9b4b32a7dbecf0e6d28be0f5b032f",
  );

  const smallCost = proposalFor(deliveryPayload, {
    move: "g1f3",
    usage: { estimated_cost_usd: 0.0000123 },
  });
  assert.equal(
    await proposalSignature(
      signingKey,
      deliveryPayload.delivery_id,
      "delivery:061b82bc",
      smallCost,
    ),
    "fb2f657e98df90403f8c50d82960ca91e427c16f79b4e16e89d3d2b689f67ca9",
  );
});

test("claims, polls, signs, and safely retries one idempotent submission", async () => {
  const calls = [];
  let submissionAttempts = 0;
  const mockFetch = async (input, init = {}) => {
    const url = new URL(input);
    calls.push({ url, init });
    if (url.pathname.endsWith("/claim")) {
      assert.deepEqual(JSON.parse(init.body), { pairing_code: "pair_secret" });
      return Response.json(credentialsPayload);
    }
    assert.match(init.headers.authorization, /^Bearer lounge_rs_/);
    if (url.pathname.endsWith("/turns/next")) {
      assert.equal(url.searchParams.get("wait_ms"), "100");
      return Response.json(deliveryPayload);
    }
    if (url.pathname.endsWith("/proposal")) {
      submissionAttempts += 1;
      if (submissionAttempts === 1) throw new TypeError("connection reset");
      const body = JSON.parse(init.body);
      assert.equal(body.idempotency_key, deliveryPayload.delivery_id);
      assert.equal(body.signature.length, 64);
      return Response.json({
        delivery_id: deliveryPayload.delivery_id,
        accepted: true,
        duplicate: true,
      });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  const client = await RunnerClient.claim("http://127.0.0.1:8000", {
    pairingId: "pairing/with slash",
    pairingCode: "pair_secret",
    fetch: mockFetch,
  });
  const delivery = await client.nextTurn(100);
  assert.ok(delivery);
  const receipt = await client.submit(delivery, proposalFor(delivery, { move: "g1f3" }));

  assert.equal(receipt.accepted, true);
  assert.equal(receipt.duplicate, true);
  assert.equal(submissionAttempts, 2);
  assert.match(calls[0].url.pathname, /pairing%2Fwith%20slash\/claim$/);
  assert.equal("runner_token" in client, false);
  assert.equal("signing_key" in client, false);
});

test("rejects plaintext remote servers and mismatched proposal binding", async () => {
  assert.throws(
    () => new RunnerClient("http://example.com", credentialsPayload),
    /must use HTTPS/,
  );
  const client = new RunnerClient("http://localhost:8000", credentialsPayload, async () => {
    throw new Error("fetch should not be called");
  });
  const proposal = proposalFor(deliveryPayload, { move: "g1f3" });
  proposal.request_id = "wrong";
  await assert.rejects(() => client.submit(deliveryPayload, proposal), /not bound/);
});
