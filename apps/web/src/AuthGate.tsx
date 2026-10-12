import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { AccountContext, authHeaders, setTokenSource, type Account } from "./auth";
import "./auth.css";

type Provider = "email" | "google" | "github";
type AuthConfig =
  | { mode: "local" }
  | { mode: "hosted"; supabase_url: string; publishable_key: string; providers: Provider[] };
type Gate =
  | { kind: "loading" }
  | { kind: "local" }
  | { kind: "error"; message: string }
  | { kind: "signed-out"; providers: Provider[] }
  | { kind: "not-invited"; email: string }
  | { kind: "ready"; account: Account };

const apiBase = import.meta.env.VITE_API_BASE ?? "";

/** Local Lounge: renders the app. Hosted Lounge: only invited, signed-in members get in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [gate, setGate] = useState<Gate>({ kind: "loading" });
  const [client, setClient] = useState<SupabaseClient | null>(null);

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;
    (async () => {
      let config: AuthConfig;
      try {
        const response = await fetch(`${apiBase}/api/auth/config`, { cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        config = (await response.json()) as AuthConfig;
      } catch {
        if (!cancelled) setGate({ kind: "error", message: "The Lounge server could not be reached. Retrying…" });
        window.setTimeout(() => window.location.reload(), 5_000);
        return;
      }
      if (config.mode === "local") {
        if (!cancelled) setGate({ kind: "local" });
        return;
      }
      // Loaded only on the hosted Lounge, so local builds never fetch the sign-in library.
      const { createClient } = await import("@supabase/supabase-js");
      const supabase = createClient(config.supabase_url, config.publishable_key, {
        auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      });
      if (cancelled) return;
      setClient(supabase);
      setTokenSource(async () => (await supabase.auth.getSession()).data.session?.access_token ?? null);
      const signOut = async () => { await supabase.auth.signOut(); };
      const evaluate = async () => {
        const { data } = await supabase.auth.getSession();
        const session = data.session;
        if (!session) { if (!cancelled) setGate({ kind: "signed-out", providers: config.providers }); return; }
        const response = await fetch(`${apiBase}/api/auth/me`, {
          cache: "no-store", headers: { Authorization: `Bearer ${session.access_token}` },
        }).catch(() => null);
        if (cancelled) return;
        if (response?.ok) {
          const me = (await response.json()) as { email: string; role: "admin" | "player" };
          setGate({ kind: "ready", account: { email: me.email, role: me.role, signOut } });
        } else if (response?.status === 403) {
          setGate({ kind: "not-invited", email: session.user.email ?? "this account" });
        } else if (response?.status === 401) {
          await supabase.auth.signOut();
        } else {
          setGate({ kind: "error", message: "The Lounge server could not be reached. Retrying…" });
          window.setTimeout(() => void evaluate(), 5_000);
        }
      };
      const { data } = supabase.auth.onAuthStateChange(event => {
        // Token refreshes keep the same person signed in; only re-check real changes.
        if (event !== "TOKEN_REFRESHED") window.setTimeout(() => void evaluate(), 0);
      });
      unsubscribe = () => data.subscription.unsubscribe();
      await evaluate();
    })();
    return () => { cancelled = true; unsubscribe?.(); };
  }, []);

  if (gate.kind === "local") return <>{children}</>;
  if (gate.kind === "ready") {
    return <AccountContext.Provider value={gate.account}>
      {window.location.pathname === "/players" && gate.account.role === "admin" ? <PlayersPage /> : children}
    </AccountContext.Provider>;
  }
  return <main className="auth-shell">
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-brand" aria-hidden="true">♞</div>
      <h1 id="auth-title">AI Chess Lounge</h1>
      {gate.kind === "loading" && <p className="auth-muted" role="status">Loading…</p>}
      {gate.kind === "error" && <p className="auth-muted" role="status">{gate.message}</p>}
      {gate.kind === "signed-out" && client && <SignIn client={client} providers={gate.providers} />}
      {gate.kind === "not-invited" && <>
        <p>You're signed in as <strong>{gate.email}</strong>, but that address hasn't been invited to this Lounge yet.</p>
        <p className="auth-muted">Ask the Lounge owner to invite it, then sign in again.</p>
        <button className="auth-secondary" onClick={() => void client?.auth.signOut()}>Use a different account</button>
      </>}
    </section>
  </main>;
}

function SignIn({ client, providers }: { client: SupabaseClient; providers: Provider[] }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<{ kind: "idle" | "sending" | "sent" } | { kind: "error"; message: string }>({ kind: "idle" });
  const returnTo = window.location.href.split("#")[0];

  async function sendLink(event: FormEvent) {
    event.preventDefault();
    setState({ kind: "sending" });
    const { error } = await client.auth.signInWithOtp({ email: email.trim(), options: { emailRedirectTo: returnTo } });
    setState(error
      ? { kind: "error", message: error.status === 429 ? "Too many sign-in emails right now. Wait a few minutes and try again." : error.message }
      : { kind: "sent" });
  }
  async function oauth(provider: "google" | "github") {
    const { error } = await client.auth.signInWithOAuth({ provider, options: { redirectTo: returnTo } });
    if (error) setState({ kind: "error", message: error.message });
  }

  return <>
    <p className="auth-muted">Invite-only. Sign in with the address the Lounge owner invited.</p>
    {providers.includes("google") && <button className="auth-provider" onClick={() => void oauth("google")}>Continue with Google</button>}
    {providers.includes("github") && <button className="auth-provider" onClick={() => void oauth("github")}>Continue with GitHub</button>}
    {providers.includes("email") && <form className="auth-email" onSubmit={sendLink}>
      {providers.length > 1 && <div className="auth-divider"><span>or</span></div>}
      <label htmlFor="auth-email">Email</label>
      <input id="auth-email" type="email" autoComplete="email" required value={email}
        onChange={event => { setEmail(event.target.value); if (state.kind !== "sending") setState({ kind: "idle" }); }} />
      <button className="auth-primary" type="submit" disabled={state.kind === "sending" || !email.trim()}>
        {state.kind === "sending" ? "Sending…" : "Email me a sign-in link"}
      </button>
    </form>}
    <p className="auth-status" role="status" aria-live="polite">
      {state.kind === "sent" && <>Check your inbox for a sign-in link. You can close this tab.</>}
      {state.kind === "error" && state.message}
    </p>
  </>;
}

type Member = { email: string; role: "admin" | "player"; status: "active" | "revoked"; signed_in: boolean; configured_admin: boolean };

/** Admin page: who may sign in. */
function PlayersPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"player" | "admin">("player");
  const [notice, setNotice] = useState<string | null>(null);
  const { request } = useApi();

  const refresh = useCallback(async () => {
    try { setMembers(await request<Member[]>("/api/admin/members")); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not load the invite list."); }
  }, [request]);
  useEffect(() => { void refresh(); }, [refresh]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    try {
      await request(`/api/admin/members/${encodeURIComponent(email.trim())}`, { method: "PUT", body: JSON.stringify({ role }) });
      setNotice(`Invited ${email.trim()}. Send them this page's address; they sign in with that email, Google or GitHub.`);
      setEmail("");
      await refresh();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Invite failed."); }
  }
  async function revoke(address: string) {
    if (!window.confirm(`Remove ${address}? They will be signed out of the Lounge on their next action.`)) return;
    try { await request(`/api/admin/members/${encodeURIComponent(address)}`, { method: "DELETE" }); await refresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Remove failed."); }
  }

  return <main className="auth-shell players-shell">
    <section className="auth-card players-card" aria-labelledby="players-title">
      <a className="auth-back" href="/">← Back to the board</a>
      <h1 id="players-title">Players</h1>
      <p className="auth-muted">Only these addresses can sign in.</p>
      <form className="players-invite" onSubmit={invite}>
        <label htmlFor="invite-email">Invite by email</label>
        <div className="players-row">
          <input id="invite-email" type="email" required value={email} onChange={event => setEmail(event.target.value)} />
          <select aria-label="Role" value={role} onChange={event => setRole(event.target.value as "player" | "admin")}>
            <option value="player">Player</option>
            <option value="admin">Admin</option>
          </select>
          <button className="auth-primary" type="submit" disabled={!email.trim()}>Invite</button>
        </div>
      </form>
      {notice && <p className="auth-status" role="status">{notice}</p>}
      {members === null ? <p className="auth-muted">Loading…</p> : <ul className="players-list" aria-label="Invited players">
        {members.map(member => <li key={member.email} className={member.status}>
          <span><strong>{member.email}</strong>
            <small>{member.role === "admin" ? "Admin" : "Player"} · {member.status === "revoked" ? "Removed" : member.signed_in ? "Has signed in" : "Invited"}</small>
          </span>
          {member.status === "active" && !member.configured_admin && <button onClick={() => void revoke(member.email)}>Remove</button>}
          {member.status === "revoked" && <button onClick={() => { setEmail(member.email); setRole(member.role); }}>Re-invite</button>}
        </li>)}
      </ul>}
    </section>
  </main>;
}

function useApi() {
  const request = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(`${apiBase}${path}`, {
      ...init, cache: "no-store",
      headers: { "Content-Type": "application/json", ...(await authHeaders()), ...init?.headers },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: unknown } | null;
      throw new Error(typeof body?.detail === "string" ? body.detail : `${response.status} ${response.statusText}`);
    }
    return (response.status === 204 ? undefined : await response.json()) as T;
  }, []);
  return { request };
}
