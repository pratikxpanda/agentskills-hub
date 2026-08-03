import { useCallback, useState } from "react";
import { createClient, identify } from "./api/client";
import type { Subscription, TeamIdentity } from "./api/types";
import { asApiError } from "./components/useAsync";
import { Failure } from "./components/widgets";
import type { ApiError } from "./api/client";
import { Catalog } from "./pages/Catalog";
import { Publish } from "./pages/Publish";
import { SkillDetail } from "./pages/SkillDetail";
import { Subscriptions } from "./pages/Subscriptions";
import { href, useRoute, type Route } from "./routes";
import { SessionContext, type Client, type Session } from "./session";

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [route, navigate] = useRoute();

  const signIn = useCallback(
    (identity: TeamIdentity, client: Client, subscriptions: Subscription[]) => {
      const build = (current: Subscription[]): Session => ({
        identity,
        client,
        subscriptions: current,
        refresh: async () => {
          const next = await client.subscriptions();
          setSession(build(next));
        },
        signOut: () => setSession(null),
      });
      setSession(build(subscriptions));
    },
    [],
  );

  if (!session) return <SignIn onSignIn={signIn} />;

  return (
    <SessionContext value={session}>
      <header className="chrome">
        <strong>Agent Skills Hub</strong>
        <nav>
          <Link route={{ name: "catalog" }} current={route} navigate={navigate}>
            Catalog
          </Link>
          <Link route={{ name: "subscriptions" }} current={route} navigate={navigate}>
            Subscriptions
          </Link>
          <Link route={{ name: "publish" }} current={route} navigate={navigate}>
            Publish
          </Link>
        </nav>
        <span className="muted">{session.identity.slug}</span>
        <button type="button" onClick={session.signOut}>
          Sign out
        </button>
      </header>

      <main>
        {route.name === "catalog" && <Catalog navigate={navigate} />}
        {route.name === "skill" && <SkillDetail skillId={route.skillId} />}
        {route.name === "subscriptions" && <Subscriptions navigate={navigate} />}
        {route.name === "publish" && <Publish />}
      </main>
    </SessionContext>
  );
}

function Link({
  route,
  current,
  navigate,
  children,
}: {
  route: Route;
  current: Route;
  navigate: (route: Route) => void;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href(route)}
      aria-current={current.name === route.name ? "page" : undefined}
      onClick={(event) => {
        event.preventDefault();
        navigate(route);
      }}
    >
      {children}
    </a>
  );
}

function SignIn({
  onSignIn,
}: {
  onSignIn: (identity: TeamIdentity, client: Client, subscriptions: Subscription[]) => void;
}) {
  const [team, setTeam] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // The team slug is asked for because the API has no "who am I" route: every endpoint is
      // scoped to a slug the caller supplies, and the credential only says yes or no to it.
      const identity = await identify(team, token);
      const client = createClient(team, token);
      onSignIn(identity, client, await client.subscriptions());
    } catch (caught: unknown) {
      setError(asApiError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="signin">
      <h1>Agent Skills Hub</h1>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="team">Team</label>
        <input
          id="team"
          value={team}
          required
          placeholder="checkout-squad"
          onChange={(event) => setTeam(event.target.value)}
        />
        <label htmlFor="token">API key</label>
        <input
          id="token"
          type="password"
          value={token}
          required
          autoComplete="off"
          onChange={(event) => setToken(event.target.value)}
        />
        <button type="submit" disabled={busy}>
          {busy ? "Checking…" : "Sign in"}
        </button>
      </form>
      <p className="muted">
        The key is held in memory for this tab only. Reloading the page asks for it again, which is
        the point.
      </p>
      {error && <Failure error={error} />}
    </main>
  );
}
