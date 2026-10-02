export const PROTOCOL_VERSION = "1.0" as const;

const SAFE_IDEMPOTENCY_KEY = /^[A-Za-z0-9._:-]{8,128}$/;
const UCI_MOVE = /^[a-h][1-8][a-h][1-8][qrbn]?$/;
const DIVISIONS = new Set([
  "pure_reasoning",
  "legal_assist",
  "tactical_metadata",
  "engine_assisted",
  "open_agentic",
  "human_ai_team",
]);

export interface UsageMetrics {
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  estimated_cost_usd: number | null;
}

export interface MoveRequest {
  schema_version: typeof PROTOCOL_VERSION;
  request_id: string;
  match_id: string;
  position_version: number;
  color: "white" | "black";
  fen: string;
  moves_uci: string[];
  pgn: string;
  legal_moves: string[] | null;
  remaining_ms: number;
  move_deadline_ms: number;
  division: string;
  public_summary_required: boolean;
}

export interface TurnDelivery {
  delivery_id: string;
  expires_at: string;
  request: MoveRequest;
}

export interface MoveProposal {
  schema_version: typeof PROTOCOL_VERSION;
  request_id: string;
  match_id: string;
  position_version: number;
  move: string;
  plan: string;
  threat: string;
  confidence: number | null;
  usage: UsageMetrics;
}

export interface ProposalOptions {
  move: string;
  plan?: string;
  threat?: string;
  confidence?: number | null;
  usage?: Partial<UsageMetrics>;
}

export interface ProposalReceipt {
  delivery_id: string;
  accepted: boolean;
  duplicate: boolean;
}

export interface RunnerCredentials {
  session_id: string;
  runner_token: string;
  signing_key: string;
  permissions: string[];
  expires_at: string;
  player: Record<string, unknown>;
  websocket_path: string;
  next_turn_path: string;
  proposal_path_template: string;
  heartbeat_path: string;
}

export interface ClaimOptions {
  pairingId: string;
  pairingCode: string;
  fetch?: typeof fetch;
}

export interface SubmitOptions {
  idempotencyKey?: string;
  transportRetries?: number;
}

export interface RunOptions {
  waitMs?: number;
  signal?: AbortSignal;
}

export type MoveHandler = (
  delivery: TurnDelivery,
) => MoveProposal | Promise<MoveProposal>;

export class RunnerProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunnerProtocolError";
  }
}

export class RunnerHttpError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`Lounge runner request failed (${status}): ${detail}`);
    this.name = "RunnerHttpError";
    this.status = status;
    this.detail = detail;
  }
}

function assertObject(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new RunnerProtocolError(`${label} must be a JSON object.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new RunnerProtocolError(`${label} must be a non-empty string.`);
  }
  return value;
}

function requiredInteger(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new RunnerProtocolError(`${label} must be an integer of at least ${minimum}.`);
  }
  return value as number;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new RunnerProtocolError(`${label} must be an array of strings.`);
  }
  return [...value];
}

function rejectUnknown(
  value: Record<string, unknown>,
  allowed: readonly string[],
  label: string,
): void {
  const allowlist = new Set(allowed);
  const unknown = Object.keys(value).filter((key) => !allowlist.has(key)).sort();
  if (unknown.length > 0) {
    throw new RunnerProtocolError(
      `${label} contains unsupported fields: ${unknown.join(", ")}.`,
    );
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new TypeError("baseUrl must be a valid HTTP(S) URL.");
  }
  const loopback = new Set(["localhost", "127.0.0.1", "[::1]"]).has(
    parsed.hostname.toLowerCase(),
  );
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new TypeError(
      "baseUrl must be an HTTP(S) server URL without credentials or query data.",
    );
  }
  if (parsed.protocol !== "https:" && !loopback) {
    throw new TypeError("Non-loopback Lounge servers must use HTTPS.");
  }
  return baseUrl.replace(/\/+$/, "");
}

function parseCredentials(raw: unknown): RunnerCredentials {
  const value = assertObject(raw, "runner credentials");
  const player = assertObject(value.player, "player");
  return {
    session_id: requiredString(value.session_id, "session_id"),
    runner_token: requiredString(value.runner_token, "runner_token"),
    signing_key: requiredString(value.signing_key, "signing_key"),
    permissions: stringArray(value.permissions, "permissions"),
    expires_at: requiredString(value.expires_at, "expires_at"),
    player: { ...player },
    websocket_path:
      typeof value.websocket_path === "string" ? value.websocket_path : "/ws/runners",
    next_turn_path:
      typeof value.next_turn_path === "string"
        ? value.next_turn_path
        : "/api/runner-sessions/turns/next",
    proposal_path_template:
      typeof value.proposal_path_template === "string"
        ? value.proposal_path_template
        : "/api/runner-sessions/turns/{delivery_id}/proposal",
    heartbeat_path:
      typeof value.heartbeat_path === "string"
        ? value.heartbeat_path
        : "/api/runner-sessions/heartbeat",
  };
}

function parseMoveRequest(raw: unknown): MoveRequest {
  const value = assertObject(raw, "turn request");
  rejectUnknown(
    value,
    [
      "schema_version",
      "request_id",
      "match_id",
      "position_version",
      "color",
      "fen",
      "moves_uci",
      "pgn",
      "legal_moves",
      "remaining_ms",
      "move_deadline_ms",
      "division",
      "public_summary_required",
    ],
    "turn request",
  );
  const schemaVersion = requiredString(value.schema_version, "schema_version");
  if (schemaVersion !== PROTOCOL_VERSION) {
    throw new RunnerProtocolError(`Unsupported protocol version: ${schemaVersion}.`);
  }
  const color = requiredString(value.color, "color");
  if (color !== "white" && color !== "black") {
    throw new RunnerProtocolError("color must be white or black.");
  }
  const division = requiredString(value.division, "division");
  if (!DIVISIONS.has(division)) {
    throw new RunnerProtocolError(`Unsupported assistance division: ${division}.`);
  }
  if (typeof value.public_summary_required !== "boolean") {
    throw new RunnerProtocolError("public_summary_required must be a boolean.");
  }
  if (typeof value.pgn !== "string") {
    throw new RunnerProtocolError("pgn must be a string.");
  }
  return {
    schema_version: PROTOCOL_VERSION,
    request_id: requiredString(value.request_id, "request_id"),
    match_id: requiredString(value.match_id, "match_id"),
    position_version: requiredInteger(value.position_version, "position_version"),
    color,
    fen: requiredString(value.fen, "fen"),
    moves_uci: stringArray(value.moves_uci, "moves_uci"),
    pgn: value.pgn,
    legal_moves:
      value.legal_moves === null ? null : stringArray(value.legal_moves, "legal_moves"),
    remaining_ms: requiredInteger(value.remaining_ms, "remaining_ms"),
    move_deadline_ms: requiredInteger(value.move_deadline_ms, "move_deadline_ms", 1),
    division,
    public_summary_required: value.public_summary_required,
  };
}

function parseDelivery(raw: unknown): TurnDelivery {
  const value = assertObject(raw, "turn delivery");
  rejectUnknown(value, ["delivery_id", "expires_at", "request"], "turn delivery");
  return {
    delivery_id: requiredString(value.delivery_id, "delivery_id"),
    expires_at: requiredString(value.expires_at, "expires_at"),
    request: parseMoveRequest(value.request),
  };
}

function parseReceipt(raw: unknown): ProposalReceipt {
  const value = assertObject(raw, "proposal receipt");
  rejectUnknown(value, ["delivery_id", "accepted", "duplicate"], "proposal receipt");
  if (typeof value.accepted !== "boolean" || typeof value.duplicate !== "boolean") {
    throw new RunnerProtocolError(
      "receipt accepted and duplicate values must be booleans.",
    );
  }
  return {
    delivery_id: requiredString(value.delivery_id, "delivery_id"),
    accepted: value.accepted,
    duplicate: value.duplicate,
  };
}

function validateMetric(value: number | null, name: string): void {
  if (value !== null && (!Number.isFinite(value) || value < 0)) {
    throw new TypeError(`${name} must be non-negative or null.`);
  }
  if (value !== null && name !== "estimated_cost_usd" && !Number.isInteger(value)) {
    throw new TypeError(`${name} must be a non-negative integer or null.`);
  }
}

export function proposalFor(
  delivery: TurnDelivery,
  options: ProposalOptions,
): MoveProposal {
  const move = options.move.trim().toLowerCase();
  const plan = options.plan ?? "";
  const threat = options.threat ?? "";
  const confidence = options.confidence ?? null;
  if (!UCI_MOVE.test(move)) {
    throw new TypeError("move must be a legal-shaped UCI move string.");
  }
  if (plan.length > 280 || threat.length > 280) {
    throw new TypeError("plan and threat must be at most 280 characters.");
  }
  if (confidence !== null && (!Number.isInteger(confidence) || confidence < 0 || confidence > 100)) {
    throw new TypeError("confidence must be an integer from 0 through 100 or null.");
  }
  const usage: UsageMetrics = {
    input_tokens: options.usage?.input_tokens ?? null,
    output_tokens: options.usage?.output_tokens ?? null,
    reasoning_tokens: options.usage?.reasoning_tokens ?? null,
    estimated_cost_usd: options.usage?.estimated_cost_usd ?? null,
  };
  for (const [name, value] of Object.entries(usage)) {
    validateMetric(value, name);
  }
  return {
    schema_version: PROTOCOL_VERSION,
    request_id: delivery.request.request_id,
    match_id: delivery.request.match_id,
    position_version: delivery.request.position_version,
    move,
    plan,
    threat,
    confidence,
    usage,
  };
}

function asciiJsonString(value: string): string {
  return JSON.stringify(value).replace(/[^\x00-\x7f]/g, (character) => {
    return `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`;
  });
}

function canonicalDecimal(value: number): string {
  if (!Number.isFinite(value)) {
    throw new TypeError("Canonical proposal numbers must be finite.");
  }
  if (Object.is(value, -0) || value === 0) return "0";
  const negative = value < 0;
  const raw = Math.abs(value).toString().toLowerCase();
  const [coefficient = "0", exponentText] = raw.split("e");
  if (exponentText === undefined) return `${negative ? "-" : ""}${coefficient}`;

  const exponent = Number.parseInt(exponentText, 10);
  const point = coefficient.indexOf(".");
  const digits = coefficient.replace(".", "");
  const decimalPosition = (point === -1 ? coefficient.length : point) + exponent;
  let expanded: string;
  if (decimalPosition <= 0) {
    expanded = `0.${"0".repeat(-decimalPosition)}${digits}`;
  } else if (decimalPosition >= digits.length) {
    expanded = `${digits}${"0".repeat(decimalPosition - digits.length)}`;
  } else {
    expanded = `${digits.slice(0, decimalPosition)}.${digits.slice(decimalPosition)}`;
  }
  return `${negative ? "-" : ""}${expanded}`;
}

function canonicalJsonAt(value: unknown, path: readonly string[]): string {
  if (value === null) return "null";
  if (typeof value === "string") return asciiJsonString(value);
  if (typeof value === "number" || typeof value === "boolean") {
    if (typeof value === "number" && path.at(-1) === "estimated_cost_usd") {
      return canonicalDecimal(value);
    }
    const encoded = JSON.stringify(value);
    if (encoded === undefined) throw new TypeError("Value is not JSON serializable.");
    return encoded;
  }
  if (Array.isArray(value)) {
    return `[${value.map((item, index) => canonicalJsonAt(item, [...path, String(index)])).join(",")}]`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${asciiJsonString(key)}:${canonicalJsonAt(record[key], [...path, key])}`)
      .join(",")}}`;
  }
  throw new TypeError("Value is not JSON serializable.");
}

export function canonicalJson(value: unknown): string {
  return canonicalJsonAt(value, []);
}

function decodeBase64Url(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  let binary: string;
  try {
    binary = atob(padded);
  } catch {
    throw new RunnerProtocolError("The runner signing key is not valid base64url.");
  }
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (bytes.byteLength !== 32) {
    throw new RunnerProtocolError("The runner signing key must decode to 32 bytes.");
  }
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

export async function proposalSignature(
  signingKey: string,
  deliveryId: string,
  idempotencyKey: string,
  proposal: MoveProposal,
): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    decodeBase64Url(signingKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const payload = new TextEncoder().encode(
    `${deliveryId}\n${idempotencyKey}\n${canonicalJson(proposal)}`,
  );
  const signature = await crypto.subtle.sign("HMAC", key, payload);
  return Array.from(new Uint8Array(signature), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

async function readJson(response: Response): Promise<unknown> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    if (response.ok) {
      throw new RunnerProtocolError("The Lounge returned a non-JSON response.");
    }
  }
  if (!response.ok) {
    const detailValue =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail?: unknown }).detail
        : undefined;
    const detail =
      typeof detailValue === "string"
        ? detailValue
        : response.statusText || "request rejected";
    throw new RunnerHttpError(response.status, detail);
  }
  return body;
}

export class RunnerClient {
  readonly baseUrl: string;
  readonly sessionId: string;
  readonly permissions: readonly string[];
  readonly expiresAt: string;
  readonly player: Readonly<Record<string, unknown>>;
  readonly #token: string;
  readonly #signingKey: string;
  readonly #paths: Pick<
    RunnerCredentials,
    "heartbeat_path" | "next_turn_path" | "proposal_path_template"
  >;
  readonly #fetch: typeof fetch;

  constructor(baseUrl: string, credentials: RunnerCredentials, fetchImpl = fetch) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.sessionId = credentials.session_id;
    this.permissions = Object.freeze([...credentials.permissions]);
    this.expiresAt = credentials.expires_at;
    this.player = Object.freeze({ ...credentials.player });
    this.#token = credentials.runner_token;
    this.#signingKey = credentials.signing_key;
    this.#paths = {
      heartbeat_path: credentials.heartbeat_path,
      next_turn_path: credentials.next_turn_path,
      proposal_path_template: credentials.proposal_path_template,
    };
    this.#fetch = fetchImpl;
  }

  static async claim(baseUrl: string, options: ClaimOptions): Promise<RunnerClient> {
    const normalized = normalizeBaseUrl(baseUrl);
    const fetchImpl = options.fetch ?? fetch;
    const response = await fetchImpl(
      `${normalized}/api/runner-pairings/${encodeURIComponent(options.pairingId)}/claim`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pairing_code: options.pairingCode }),
        redirect: "error",
      },
    );
    return new RunnerClient(normalized, parseCredentials(await readJson(response)), fetchImpl);
  }

  async heartbeat(): Promise<Record<string, unknown>> {
    const response = await this.#fetch(this.#url(this.#paths.heartbeat_path), {
      method: "POST",
      headers: this.#headers(),
      redirect: "error",
    });
    return assertObject(await readJson(response), "heartbeat response");
  }

  async nextTurn(waitMs = 25_000): Promise<TurnDelivery | null> {
    if (!Number.isInteger(waitMs) || waitMs < 0 || waitMs > 25_000) {
      throw new RangeError("waitMs must be an integer from 0 through 25000.");
    }
    const url = new URL(this.#url(this.#paths.next_turn_path));
    url.searchParams.set("wait_ms", String(waitMs));
    const response = await this.#fetch(url, {
      method: "GET",
      headers: this.#headers(),
      redirect: "error",
    });
    if (response.status === 204) return null;
    return parseDelivery(await readJson(response));
  }

  async submit(
    delivery: TurnDelivery,
    proposal: MoveProposal,
    options: SubmitOptions = {},
  ): Promise<ProposalReceipt> {
    this.#validateBinding(delivery, proposal);
    const idempotencyKey = options.idempotencyKey ?? delivery.delivery_id;
    if (!SAFE_IDEMPOTENCY_KEY.test(idempotencyKey)) {
      throw new TypeError("idempotencyKey must be 8-128 safe ASCII characters.");
    }
    const transportRetries = options.transportRetries ?? 1;
    if (!Number.isInteger(transportRetries) || transportRetries < 0 || transportRetries > 3) {
      throw new RangeError("transportRetries must be an integer from 0 through 3.");
    }
    const body = JSON.stringify({
      idempotency_key: idempotencyKey,
      proposal,
      signature: await proposalSignature(
        this.#signingKey,
        delivery.delivery_id,
        idempotencyKey,
        proposal,
      ),
    });
    const path = this.#paths.proposal_path_template.replace(
      "{delivery_id}",
      encodeURIComponent(delivery.delivery_id),
    );
    let response: Response | undefined;
    for (let attempt = 0; attempt <= transportRetries; attempt += 1) {
      try {
        response = await this.#fetch(this.#url(path), {
          method: "POST",
          headers: { ...this.#headers(), "content-type": "application/json" },
          body,
          redirect: "error",
        });
        break;
      } catch (error) {
        if (attempt >= transportRetries) throw error;
        await Promise.resolve();
      }
    }
    if (response === undefined) {
      throw new RunnerProtocolError("The proposal request did not produce a response.");
    }
    return parseReceipt(await readJson(response));
  }

  async run(handler: MoveHandler, options: RunOptions = {}): Promise<void> {
    const waitMs = options.waitMs ?? 25_000;
    while (!options.signal?.aborted) {
      const delivery = await this.nextTurn(waitMs);
      if (delivery === null) continue;
      const proposal = await handler(delivery);
      await this.submit(delivery, proposal);
    }
  }

  #headers(): Record<string, string> {
    return { authorization: `Bearer ${this.#token}` };
  }

  #url(path: string): string {
    if (!path.startsWith("/")) {
      throw new RunnerProtocolError("Runner endpoint paths must start with '/'.");
    }
    return `${this.baseUrl}${path}`;
  }

  #validateBinding(delivery: TurnDelivery, proposal: MoveProposal): void {
    const request = delivery.request;
    if (
      proposal.request_id !== request.request_id ||
      proposal.match_id !== request.match_id ||
      proposal.position_version !== request.position_version
    ) {
      throw new RunnerProtocolError("The proposal is not bound to the delivered turn.");
    }
  }
}
