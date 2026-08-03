import { useState } from "react";
import type { CatalogSkill } from "../api/types";
import { Failure, Loading, Tags } from "../components/widgets";
import { useAsync } from "../components/useAsync";
import { useSession } from "../session";
import type { Route } from "../routes";

export function Catalog({ navigate }: { navigate: (route: Route) => void }) {
  const { client } = useSession();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [tag, setTag] = useState<string | null>(null);

  // One request renders the page: the catalog already carries the calling team's subscription
  // state, so no card has to ask a follow-up question about itself.
  const page = useAsync(`catalog:${submitted}:${tag ?? ""}`, () =>
    client.catalog(tag ? { q: submitted, tags: [tag] } : { q: submitted }),
  );

  return (
    <section>
      <form
        className="search"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(query);
        }}
      >
        <input
          type="search"
          value={query}
          placeholder="Search skills"
          aria-label="Search skills"
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit">Search</button>
        {tag && (
          <button type="button" onClick={() => setTag(null)}>
            Clear tag: {tag}
          </button>
        )}
      </form>

      {page.loading && <Loading what="the catalog" />}
      {page.error && <Failure error={page.error} />}
      {page.data &&
        (page.data.items.length === 0 ? (
          <p className="muted">No skills match. An empty catalog is an answer, not an error.</p>
        ) : (
          <ul className="cards">
            {page.data.items.map((skill) => (
              <SkillCard key={skill.skill_id} skill={skill} navigate={navigate} onTag={setTag} />
            ))}
          </ul>
        ))}
      {page.data?.next_cursor && (
        <p className="muted">More results exist. Narrow the search to see them.</p>
      )}
    </section>
  );
}

function SkillCard({
  skill,
  navigate,
  onTag,
}: {
  skill: CatalogSkill;
  navigate: (route: Route) => void;
  onTag: (tag: string) => void;
}) {
  return (
    <li className="card">
      <h2>
        <a
          href={`/skills/${encodeURIComponent(skill.skill_id)}`}
          onClick={(event) => {
            event.preventDefault();
            navigate({ name: "skill", skillId: skill.skill_id });
          }}
        >
          {skill.skill_id}
        </a>
      </h2>
      <p>{skill.description}</p>
      <dl>
        <dt>Owner</dt>
        <dd>{skill.owner}</dd>
        <dt>Latest</dt>
        <dd>{skill.latest_version}</dd>
        <dt>Subscribers</dt>
        <dd>{skill.subscriber_count}</dd>
      </dl>
      <Tags tags={skill.tags} onSelect={onTag} />
      {skill.is_subscribed ? (
        <p className="pinned">Subscribed at {skill.subscribed_version}</p>
      ) : (
        <p className="muted">Not subscribed</p>
      )}
      {skill.lifecycle !== "active" && <p className="warn">{skill.lifecycle}</p>}
    </li>
  );
}
