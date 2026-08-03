import { createContext, use } from "react";
import type { createClient } from "./api/client";
import type { Subscription, TeamIdentity } from "./api/types";

export type Client = ReturnType<typeof createClient>;

export interface Session {
  identity: TeamIdentity;
  client: Client;
  subscriptions: Subscription[];
  refresh: () => Promise<void>;
  signOut: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = use(SessionContext);
  if (!session) throw new Error("useSession outside a signed-in tree");
  return session;
}

/**
 * The API key lives here and nowhere else — not in `localStorage`, not in `sessionStorage`, not
 * in a cookie. A stored key is a key that outlives the tab it was pasted into, and the same XSS
 * that this app spends its effort preventing would be the thing that reads it.
 */
export function mcpUrl(team: string): string {
  return `${window.location.origin}/mcp/${encodeURIComponent(team)}`;
}
