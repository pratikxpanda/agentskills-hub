import { useState } from "react";
import { asApiError } from "../components/useAsync";
import { useAsync } from "../components/useAsync";
import { Failure, Loading, Markdown, Tags } from "../components/widgets";
import type { ApiError } from "../api/client";
import { useSession } from "../session";

export function SkillDetail({ skillId }: { skillId: string }) {
  const { client, subscriptions, refresh } = useSession();
  const [reload, setReload] = useState(0);
  const skill = useAsync(`skill:${skillId}:${reload}`, () => client.skill(skillId));
  const versions = useAsync(`versions:${skillId}:${reload}`, () => client.versions(skillId));

  const pinned = subscriptions.find((subscription) => subscription.skill_id === skillId);

  return (
    <section>
      {skill.loading && <Loading what={skillId} />}
      {skill.error && <Failure error={skill.error} />}
      {skill.data && (
        <>
          <header>
            <h1>{skill.data.skill_id}</h1>
            <p>{skill.data.description}</p>
            <p className="muted">
              Owned by {skill.data.owner} · {skill.data.subscriber_count} subscribers ·{" "}
              {skill.data.lifecycle}
            </p>
            <Tags tags={skill.data.tags} />
          </header>

          <Subscribe
            skillId={skillId}
            pinnedVersion={pinned?.version ?? null}
            latest={skill.data.latest_version}
            versions={versions.data?.map((version) => version.version) ?? []}
            onChange={async () => {
              await refresh();
              setReload((value) => value + 1);
            }}
          />

          <h2>Body</h2>
          <Markdown source={skill.data.body} />

          <h2>Resources</h2>
          <Resources resources={skill.data.resources} />

          <h2>Versions</h2>
          {versions.error && <Failure error={versions.error} />}
          <table>
            <thead>
              <tr>
                <th>Version</th>
                <th>Published</th>
                <th>By</th>
                <th>Digest</th>
              </tr>
            </thead>
            <tbody>
              {(versions.data ?? []).map((version) => (
                <tr key={version.version}>
                  <td>{version.version}</td>
                  <td>{version.published_at?.slice(0, 10) ?? "—"}</td>
                  <td>{version.published_by ?? "—"}</td>
                  <td className="code">{version.content_digest.slice(0, 12)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function Resources({ resources }: { resources: Record<string, string[]> }) {
  const kinds = Object.entries(resources).filter(([, files]) => files.length > 0);
  if (kinds.length === 0) return <p className="muted">None.</p>;
  return (
    <dl>
      {kinds.map(([kind, files]) => (
        <div key={kind}>
          <dt>{kind}</dt>
          <dd>
            <ul>
              {files.map((file) => (
                <li key={file} className="code">
                  {file}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Subscribe({
  skillId,
  pinnedVersion,
  latest,
  versions,
  onChange,
}: {
  skillId: string;
  pinnedVersion: string | null;
  latest: string;
  versions: string[];
  onChange: () => Promise<void>;
}) {
  const { client } = useSession();
  const [choice, setChoice] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const options = versions.length > 0 ? versions : [latest];
  const selected = choice ?? pinnedVersion ?? latest;

  async function act(run: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await run();
      await onChange();
    } catch (caught: unknown) {
      setError(asApiError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="subscribe">
      <label>
        <span>Version</span>
        <select value={selected} onChange={(event) => setChoice(event.target.value)}>
          {options.map((version) => (
            <option key={version} value={version}>
              {version}
              {version === latest ? " (latest)" : ""}
            </option>
          ))}
        </select>
      </label>

      {pinnedVersion === null ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void act(() => client.subscribe(skillId, selected))}
        >
          Subscribe
        </button>
      ) : (
        <>
          <button
            type="button"
            disabled={busy || selected === pinnedVersion}
            onClick={() => void act(() => client.repin(skillId, selected))}
          >
            Change pin to {selected}
          </button>
          <button type="button" disabled={busy} onClick={() => void act(() => client.unsubscribe(skillId))}>
            Unsubscribe
          </button>
        </>
      )}

      {pinnedVersion && <p className="pinned">Pinned to {pinnedVersion}</p>}
      {error && <Failure error={error} />}
    </div>
  );
}
