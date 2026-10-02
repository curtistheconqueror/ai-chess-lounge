import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";

import { RunnerClient, proposalFor } from "./dist/index.js";

function argument(name, fallback = undefined) {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const baseUrl = argument("base-url", "http://127.0.0.1:8000");
const pairingId = argument("pairing-id");
if (!pairingId) {
  console.error("Usage: npm run sample -- --base-url URL --pairing-id PAIRING_ID");
  process.exitCode = 2;
} else {
  const prompt = createInterface({ input: stdin, output: stdout });
  const pairingCode = await prompt.question("One-time pairing code: ");
  prompt.close();

  const client = await RunnerClient.claim(baseUrl, { pairingId, pairingCode });
  const displayName = client.player.display_name ?? "remote runner";
  console.log(`Paired ${displayName}; waiting for turns. Press Ctrl+C to stop.`);

  await client.run(async (delivery) => {
    const move = delivery.request.legal_moves?.[0];
    if (!move) {
      throw new Error(
        "The sample bot requires a Legal Assist seat with legal_moves enabled.",
      );
    }
    return proposalFor(delivery, {
      move,
      plan: "Play the first deterministic legal move from the disclosed move list.",
      threat: "This sample demonstrates transport, not chess strength.",
      confidence: 25,
    });
  });
}
