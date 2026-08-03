import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { CatalogSkill, Subscription } from "../api/types";

const SKILL: CatalogSkill = {
  skill_id: "incident-response",
  description: "What to do when the pager goes off.",
  owner: "platform-team",
  scope: "org",
  lifecycle: "active",
  subscription_model: "open",
  tags: ["operations"],
  latest_version: "2.0.0",
  published_at: "2026-01-01T00:00:00Z",
  subscriber_count: 3,
  is_subscribed: false,
  subscribed_version: null,
};

const SUBSCRIPTION: Subscription = {
  skill_id: "incident-response",
  owner: "platform-team",
  description: SKILL.description,
  version: "1.0.0",
  latest_version: "2.0.0",
  update_available: true,
  lifecycle: "active",
  origin: "manual",
  subscribed_at: "2026-02-01T00:00:00Z",
  subscribed_by: "abc123",
  updated_at: null,
  updated_by: null,
};

const calls: string[] = [];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function pathOf(input: URL | RequestInfo): string {
  if (typeof input === "string") return input;
  return input instanceof URL ? `${input.pathname}${input.search}` : input.url;
}

function route(path: string, subscriptions: Subscription[]): Response {
  if (path.startsWith("/api/teams/checkout-squad/subscriptions")) return json(subscriptions);
  if (path === "/api/teams/checkout-squad") {
    return json({ team_id: "t", slug: "checkout-squad", environment_id: "e" });
  }
  if (path.startsWith("/api/skills?") || path === "/api/skills") {
    return json({ items: [SKILL], next_cursor: null });
  }
  return json({ error: { code: "not_found", message: "No route in the stub.", details: [] } }, 404);
}

beforeEach(() => {
  calls.length = 0;
  window.history.pushState(null, "", "/");
  vi.stubGlobal(
    "fetch",
    vi.fn((input: URL | RequestInfo) => {
      const path = pathOf(input);
      calls.push(path);
      return Promise.resolve(route(path, [SUBSCRIPTION]));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

async function signIn() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText("Team"), "checkout-squad");
  await user.type(screen.getByLabelText("API key"), "ashub_deadbeefcafe_secret");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByRole("heading", { name: "incident-response" });
  return user;
}

describe("App", () => {
  it("renders the catalog from a single request", async () => {
    await signIn();

    expect(calls.filter((path) => path.startsWith("/api/skills"))).toHaveLength(1);
    expect(screen.getByText(SKILL.description)).toBeInTheDocument();
    expect(screen.getByText("Not subscribed")).toBeInTheDocument();
  });

  it("never persists the API key", async () => {
    await signIn();

    // Both stores are asserted, not just localStorage: the point is that the key does not
    // outlive the tab, and sessionStorage would be the obvious place to put it back.
    expect(Object.keys(localStorage)).toHaveLength(0);
    expect(Object.keys(sessionStorage)).toHaveLength(0);
    expect(JSON.stringify(localStorage) + JSON.stringify(sessionStorage)).not.toContain("ashub_");
  });

  it("sends the credential as a bearer token and nothing else", async () => {
    await signIn();
    const request = vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit;

    expect(request.headers).toMatchObject({ Authorization: "Bearer ashub_deadbeefcafe_secret" });
    expect(request.credentials).toBeUndefined();
  });

  it("shows the team's MCP endpoint and its pinned versions", async () => {
    const user = await signIn();
    await user.click(screen.getByRole("link", { name: "Subscriptions" }));

    const url = await screen.findByLabelText("MCP endpoint");
    expect(url).toHaveValue(`${window.location.origin}/mcp/checkout-squad`);
    expect(screen.getByText("update available")).toBeInTheDocument();
  });

  it("reports a refused publish against the field that caused it", async () => {
    const user = await signIn();
    vi.mocked(fetch).mockImplementation((input: URL | RequestInfo) =>
      Promise.resolve(
        pathOf(input) === "/api/skills"
          ? json(
              {
                error: {
                  code: "invalid_skill",
                  message: "The archive is not a valid skill.",
                  details: ["SKILL.md: missing frontmatter key 'description'"],
                },
              },
              400,
            )
          : route(pathOf(input), [SUBSCRIPTION]),
      ),
    );

    await user.click(screen.getByRole("link", { name: "Publish" }));
    await user.type(screen.getByLabelText("Skill id"), "incident-response");
    await user.type(screen.getByLabelText("Version"), "1.0.0");
    await user.upload(
      screen.getByLabelText("Archive"),
      new File(["x"], "skill.tar.gz", { type: "application/gzip" }),
    );
    await user.click(screen.getByRole("button", { name: "Publish" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The archive is not a valid skill.");
    expect(alert).toHaveTextContent("missing frontmatter key");
    await waitFor(() =>
      expect(screen.getByLabelText("Archive").closest(".field")).toHaveClass("invalid"),
    );
  });
});
