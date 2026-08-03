import type {
  CatalogPage,
  PublishedSkill,
  SkillDetail,
  SkillVersionSummary,
  Subscription,
  TeamIdentity,
} from "./types";

/** The API's error envelope, kept whole so a caller can show the details it carries. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface Envelope {
  error?: { code?: string; message?: string; details?: unknown };
}

async function toError(response: Response): Promise<ApiError> {
  let body: Envelope = {};
  try {
    body = (await response.json()) as Envelope;
  } catch {
    // A proxy or a crash can answer with something that is not the envelope.
  }
  const error = body.error ?? {};
  const details = Array.isArray(error.details) ? error.details.map(String) : [];
  return new ApiError(
    response.status,
    error.code ?? "unexpected",
    error.message ?? `${response.status} ${response.statusText}`,
    details,
  );
}

export interface HubClient {
  team: string;
  catalog(query: { q?: string; tags?: string[] }): Promise<CatalogPage>;
  skill(skillId: string): Promise<SkillDetail>;
  versions(skillId: string): Promise<SkillVersionSummary[]>;
  subscriptions(): Promise<Subscription[]>;
  subscribe(skillId: string, version: string): Promise<Subscription>;
  repin(skillId: string, version: string): Promise<Subscription>;
  unsubscribe(skillId: string): Promise<void>;
  publish(form: FormData): Promise<PublishedSkill>;
}

export function identify(team: string, token: string, fetcher = fetch): Promise<TeamIdentity> {
  return createClient(team, token, fetcher).request<TeamIdentity>(
    "GET",
    `/api/teams/${encodeURIComponent(team)}`,
  );
}

export function createClient(team: string, token: string, fetcher = fetch) {
  async function request<T>(method: string, path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetcher(path, {
      ...init,
      method,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      throw await toError(response);
    }
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }

  const json = (body: unknown): RequestInit => ({
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const scoped = `/api/teams/${encodeURIComponent(team)}/subscriptions`;

  return {
    team,
    request,
    catalog({ q, tags }: { q?: string; tags?: string[] }) {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      for (const tag of tags ?? []) params.append("tags", tag);
      const query = params.toString();
      return request<CatalogPage>("GET", `/api/skills${query ? `?${query}` : ""}`);
    },
    skill(skillId: string) {
      return request<SkillDetail>("GET", `/api/skills/${encodeURIComponent(skillId)}`);
    },
    versions(skillId: string) {
      return request<SkillVersionSummary[]>(
        "GET",
        `/api/skills/${encodeURIComponent(skillId)}/versions`,
      );
    },
    subscriptions() {
      return request<Subscription[]>("GET", scoped);
    },
    subscribe(skillId: string, version: string) {
      return request<Subscription>("POST", scoped, json({ skill_id: skillId, version }));
    },
    repin(skillId: string, version: string) {
      return request<Subscription>(
        "PATCH",
        `${scoped}/${encodeURIComponent(skillId)}`,
        json({ version }),
      );
    },
    unsubscribe(skillId: string) {
      return request<void>("DELETE", `${scoped}/${encodeURIComponent(skillId)}`);
    },
    publish(form: FormData) {
      return request<PublishedSkill>("POST", "/api/skills", { body: form });
    },
  };
}
