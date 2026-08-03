import { useState } from "react";
import type { ApiError } from "../api/client";
import { asApiError } from "../components/useAsync";
import { Copyable, Failure } from "../components/widgets";
import type { Route } from "../routes";
import { mcpUrl, useSession } from "../session";

export function Subscriptions({ navigate }: { navigate: (route: Route) => void }) {
  const { client, identity, subscriptions, refresh } = useSession();
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function act(skillId: string, run: () => Promise<unknown>) {
    setBusy(skillId);
    setError(null);
    try {
      await run();
      await refresh();
    } catch (caught: unknown) {
      setError(asApiError(caught));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section>
      <h1>Subscriptions</h1>

      <p className="muted">
        Point an agent at this URL. It serves exactly the skills below, at exactly these versions.
      </p>
      <Copyable label="MCP endpoint" value={mcpUrl(identity.slug)} />

      {error && <Failure error={error} />}

      {subscriptions.length === 0 ? (
        <p className="muted">
          Nothing subscribed yet. The endpoint above still works — it serves an empty catalog.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Skill</th>
              <th>Pinned</th>
              <th>Latest</th>
              <th>Subscribed</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {subscriptions.map((subscription) => (
              <tr key={subscription.skill_id}>
                <td>
                  <a
                    href={`/skills/${encodeURIComponent(subscription.skill_id)}`}
                    onClick={(event) => {
                      event.preventDefault();
                      navigate({ name: "skill", skillId: subscription.skill_id });
                    }}
                  >
                    {subscription.skill_id}
                  </a>
                  <p className="muted">{subscription.description}</p>
                </td>
                <td>{subscription.version}</td>
                <td>
                  {subscription.latest_version ?? "—"}
                  {subscription.update_available && <span className="warn"> update available</span>}
                </td>
                <td className="muted">
                  {subscription.subscribed_at.slice(0, 10)}
                  {subscription.subscribed_by && ` by ${subscription.subscribed_by}`}
                </td>
                <td>
                  {subscription.update_available && subscription.latest_version && (
                    <button
                      type="button"
                      disabled={busy === subscription.skill_id}
                      onClick={() =>
                        void act(subscription.skill_id, () =>
                          client.repin(subscription.skill_id, subscription.latest_version!),
                        )
                      }
                    >
                      Upgrade
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy === subscription.skill_id}
                    onClick={() =>
                      void act(subscription.skill_id, () =>
                        client.unsubscribe(subscription.skill_id),
                      )
                    }
                  >
                    Unsubscribe
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
