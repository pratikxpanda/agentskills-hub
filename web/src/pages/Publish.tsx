import { useState } from "react";
import { ApiError } from "../api/client";
import { asApiError } from "../components/useAsync";
import { Failure } from "../components/widgets";
import type { PublishedSkill } from "../api/types";
import { useSession } from "../session";

/** Which field a refusal is about, so it can be shown where the mistake was made. */
const FIELD_OF: Record<string, "skill_id" | "version" | "tags" | "archive"> = {
  invalid_identifier: "skill_id",
  version_exists: "version",
  skill_conflict: "skill_id",
  invalid_tags: "tags",
  invalid_skill: "archive",
  unsupported_archive: "archive",
  archive_rejected: "archive",
};

export function Publish() {
  const { client, refresh } = useSession();
  const [error, setError] = useState<ApiError | null>(null);
  const [published, setPublished] = useState<PublishedSkill | null>(null);
  const [busy, setBusy] = useState(false);

  const field = error ? FIELD_OF[error.code] : undefined;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = event.currentTarget.elements;
    const value = (name: string) => (fields.namedItem(name) as HTMLInputElement).value.trim();
    const archive = (fields.namedItem("archive") as HTMLInputElement).files?.[0];

    if (!archive) {
      // Reported like every other refusal rather than as a browser tooltip, so the page has one
      // way of saying no.
      setError(new ApiError(0, "unsupported_archive", "Choose an archive to publish."));
      return;
    }

    const form = new FormData();
    form.set("skill_id", value("skill_id"));
    form.set("version", value("version"));
    form.set(
      "tags",
      JSON.stringify(
        value("tags")
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      ),
    );
    form.set("archive", archive);

    setBusy(true);
    setError(null);
    setPublished(null);
    try {
      setPublished(await client.publish(form));
      await refresh();
    } catch (caught: unknown) {
      setError(asApiError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Publish</h1>
      <p className="muted">
        A <code>tar.gz</code> or <code>zip</code> of the skill folder. The version is immutable
        once published.
      </p>

      <form onSubmit={(event) => void submit(event)} className="publish">
        <Field name="skill_id" label="Skill id" error={field === "skill_id" ? error : null}>
          <input id="skill_id" name="skill_id" required placeholder="incident-response" />
        </Field>
        <Field name="version" label="Version" error={field === "version" ? error : null}>
          <input id="version" name="version" required placeholder="1.0.0" />
        </Field>
        <Field name="tags" label="Tags" error={field === "tags" ? error : null}>
          <input id="tags" name="tags" placeholder="operations, oncall" />
        </Field>
        <Field name="archive" label="Archive" error={field === "archive" ? error : null}>
          <input
            id="archive"
            name="archive"
            type="file"
            accept="application/gzip,application/zip,.gz,.tgz,.zip"
          />
        </Field>

        <button type="submit" disabled={busy}>
          {busy ? "Publishing…" : "Publish"}
        </button>
      </form>

      {error && !field && <Failure error={error} />}
      {published && (
        <p className="pinned">
          Published {published.skill_id} {published.version} · {published.content_digest.slice(0, 12)}
        </p>
      )}
    </section>
  );
}

function Field({
  name,
  label,
  error,
  children,
}: {
  name: string;
  label: string;
  error: ApiError | null;
  children: React.ReactNode;
}) {
  return (
    <div className={error ? "field invalid" : "field"}>
      <label htmlFor={name}>{label}</label>
      {children}
      {error && (
        <div className="field-error" role="alert">
          <p>{error.message}</p>
          {error.details.length > 0 && (
            <ul>
              {error.details.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
