import { createContext, useContext } from "react";

/** Who is signed in on the hosted Lounge; null on a local Lounge (no accounts). */
export type Account = { email: string; role: "admin" | "player"; signOut: () => Promise<void> };

export const AccountContext = createContext<Account | null>(null);
export const useAccount = () => useContext(AccountContext);

// The hosted sign-in session supplies the access token; local mode has none.
let tokenSource: (() => Promise<string | null>) | null = null;
let lastToken: string | null = null;

export function setTokenSource(source: (() => Promise<string | null>) | null): void {
  tokenSource = source;
  lastToken = null;
}

export async function authHeaders(): Promise<Record<string, string>> {
  if (!tokenSource) return {};
  lastToken = await tokenSource();
  return lastToken ? { Authorization: `Bearer ${lastToken}` } : {};
}

/** For a request sent while the page unloads, which cannot wait for a token refresh. */
export function cachedAuthHeaders(): Record<string, string> {
  return lastToken ? { Authorization: `Bearer ${lastToken}` } : {};
}

export const hostedMode = () => tokenSource !== null;
