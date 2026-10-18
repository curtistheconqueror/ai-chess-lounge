import { expect, test, type Page } from "@playwright/test";
import { finishFixtureGames } from "./fixture-games";

// The fixture server runs in local mode; these tests stand in for the hosted server's
// auth answers and for Supabase, so the sign-in screens can be exercised without accounts.
const SUPABASE = "https://abcdefghijklmnopqrst.supabase.co";
const STORAGE_KEY = "sb-abcdefghijklmnopqrst-auth-token";
const config = { mode: "hosted", supabase_url: SUPABASE, publishable_key: "sb_publishable_test", providers: ["email", "google", "github"] };

test.beforeEach(async ({ request }) => { await finishFixtureGames(request); });

async function hosted(page: Page, me: { status: number; body?: object }) {
  await page.route("**/api/auth/config", route => route.fulfill({ json: config }));
  await page.route("**/api/auth/me", route => route.fulfill({ status: me.status, json: me.body ?? { detail: "This account has not been invited to the Lounge." } }));
  await page.route("**/api/ws-ticket", route => route.fulfill({ json: { ticket: "fixture-ticket" } }));
  await page.route(`${SUPABASE}/**`, route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/auth/v1/otp") return route.fulfill({ json: {} });
    if (url.pathname === "/auth/v1/logout") return route.fulfill({ status: 204, body: "" });
    if (url.pathname === "/auth/v1/authorize") return route.fulfill({ contentType: "text/html", body: `<h1>Provider ${url.searchParams.get("provider")}</h1>` });
    return route.fulfill({ status: 404, json: {} });
  });
}

async function signedIn(page: Page, email = "owner@example.com") {
  await page.addInitScript(([key, address]) => {
    const now = Math.floor(Date.now() / 1000);
    localStorage.setItem(key, JSON.stringify({
      access_token: "fixture-access-token", refresh_token: "fixture-refresh", token_type: "bearer",
      expires_in: 3600, expires_at: now + 3600,
      user: { id: "11111111-1111-1111-1111-111111111111", email: address, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: new Date().toISOString() },
    }));
  }, [STORAGE_KEY, email] as const);
}

test("signed out: invite-only sign-in offers Google, GitHub and an email link", async ({ page }) => {
  await hosted(page, { status: 401 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AI Chess Lounge" })).toBeVisible();
  await expect(page.getByText(/Invite-only/)).toBeVisible();
  await expect(page.locator(".board")).toHaveCount(0);
  const otp = page.waitForRequest(request => request.url().startsWith(`${SUPABASE}/auth/v1/otp`));
  await page.getByLabel("Email").fill("friend@example.com");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  expect((await otp).postDataJSON().email).toBe("friend@example.com");
  await expect(page.getByRole("status")).toContainText("Check your inbox");
  await page.getByRole("button", { name: "Continue with GitHub" }).click();
  await expect(page.getByRole("heading", { name: "Provider github" })).toBeVisible();
});

test("signed in but not invited: explains and offers another account", async ({ page }) => {
  await hosted(page, { status: 403 });
  await signedIn(page, "stranger@example.com");
  await page.goto("/");
  await expect(page.getByText("stranger@example.com")).toBeVisible();
  await expect(page.getByText(/hasn't been invited/)).toBeVisible();
  await expect(page.locator(".board")).toHaveCount(0);
  await page.getByRole("button", { name: "Use a different account" }).click();
  await expect(page.getByRole("button", { name: "Email me a sign-in link" })).toBeVisible();
});

test("invited player: the board, a hosted account menu and only Stockfish seats; API calls carry the sign-in", async ({ page }) => {
  await hosted(page, { status: 200, body: { email: "player@example.com", role: "player" } });
  await signedIn(page, "player@example.com");
  const authorized = page.waitForRequest(request => request.url().includes("/api/table-settings") && request.headers().authorization === "Bearer fixture-access-token");
  await page.goto("/");
  await authorized;
  await expect(page.locator(".board")).toBeVisible();
  await page.getByText("Account", { exact: true }).click();
  await expect(page.getByLabel("Signed in as")).toHaveText("player@example.com");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Players" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Model Lab" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByText("Connections & API access")).toHaveCount(0);
  const seats = await page.getByLabel("White seat").locator("option").allTextContents();
  expect(seats).toEqual(["Human player", "Stockfish"]);
  // The live board opens its socket with a one-time ticket.
  const socket = page.waitForEvent("websocket", ws => ws.url().includes("ticket=fixture-ticket"));
  const game = await (await page.request.post("/api/games", { data: { opponent: "human", initial_time_ms: 600_000 } })).json();
  await page.goto(`/games/${game.id}`);
  await socket;
  await expect(page.getByLabel("Connection live")).toBeVisible();
  // Signing out returns to the sign-in screen.
  await page.getByText("Account", { exact: true }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Email me a sign-in link" })).toBeVisible();
});

test("admin: Players page invites and removes members", async ({ page }) => {
  await hosted(page, { status: 200, body: { email: "owner@example.com", role: "admin" } });
  await signedIn(page);
  const members = [
    { email: "owner@example.com", role: "admin", status: "active", signed_in: true, configured_admin: true },
    { email: "bob@example.com", role: "player", status: "active", signed_in: false, configured_admin: false },
  ];
  const calls: string[] = [];
  await page.route("**/api/admin/members**", async route => {
    const request = route.request();
    if (request.method() === "GET") return route.fulfill({ json: members });
    calls.push(`${request.method()} ${decodeURIComponent(new URL(request.url()).pathname)} ${request.headers().authorization}`);
    if (request.method() === "PUT") members.push({ email: "carol@example.com", role: "player", status: "active", signed_in: false, configured_admin: false });
    if (request.method() === "DELETE") members[1].status = "revoked";
    return route.fulfill({ status: 204, body: "" });
  });
  await page.goto("/");
  await page.getByText("Account", { exact: true }).click();
  await page.getByRole("link", { name: "Players" }).click();
  await expect(page.getByRole("heading", { name: "Players" })).toBeVisible();
  const list = page.getByRole("list", { name: "Invited players" });
  await expect(list.getByRole("listitem")).toHaveCount(2);
  // A configured admin cannot be removed from the page.
  await expect(list.getByRole("listitem").first().getByRole("button")).toHaveCount(0);
  await page.getByLabel("Invite by email").fill("carol@example.com");
  await page.getByRole("button", { name: "Invite", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Invited carol@example.com");
  await expect(list.getByRole("listitem")).toHaveCount(3);
  page.once("dialog", dialog => void dialog.accept());
  await list.getByRole("listitem").filter({ hasText: "bob@example.com" }).getByRole("button", { name: "Remove" }).click();
  await expect(list.getByRole("listitem").filter({ hasText: "bob@example.com" })).toContainText("Removed");
  expect(calls).toEqual([
    "PUT /api/admin/members/carol@example.com Bearer fixture-access-token",
    "DELETE /api/admin/members/bob@example.com Bearer fixture-access-token",
  ]);
});
