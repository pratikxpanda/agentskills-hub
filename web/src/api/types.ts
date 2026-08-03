export type Lifecycle = "active" | "deprecated" | "archived";

export interface CatalogSkill {
  skill_id: string;
  description: string;
  owner: string;
  scope: string;
  lifecycle: Lifecycle;
  subscription_model: string;
  tags: string[];
  latest_version: string;
  published_at: string | null;
  subscriber_count: number;
  is_subscribed: boolean;
  subscribed_version: string | null;
}

export interface CatalogPage {
  items: CatalogSkill[];
  next_cursor: string | null;
}

export interface SkillDetail extends CatalogSkill {
  body: string;
  resources: Record<string, string[]>;
}

export interface SkillVersionSummary {
  version: string;
  description: string;
  content_digest: string;
  catalog_tokens: number;
  published_at: string | null;
  published_by: string | null;
}

export interface Subscription {
  skill_id: string;
  owner: string;
  description: string;
  version: string;
  latest_version: string | null;
  update_available: boolean;
  lifecycle: Lifecycle;
  origin: string;
  subscribed_at: string;
  subscribed_by: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface TeamIdentity {
  team_id: string;
  slug: string;
  environment_id: string;
}

export interface PublishedSkill {
  skill_id: string;
  version: string;
  content_digest: string;
  description: string;
  owner_team_id: string;
  version_id: string;
}
