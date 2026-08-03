import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../markdown";

/**
 * Stored XSS here would run in the session of someone who can publish to every agent in the
 * organization, so each fixture is a payload that has worked against a real markdown pipeline
 * at some point. The assertions are on what survives, not on the exact escaping.
 */
const PAYLOADS: Record<string, string> = {
  "script tag": "<script>alert(1)</script>",
  "img onerror": '<img src=x onerror="alert(1)">',
  "svg onload": '<svg/onload=alert(1)>',
  iframe: '<iframe src="javascript:alert(1)"></iframe>',
  "style block": "<style>body{display:none}</style>",
  "inline event on markdown link": "[click](javascript:alert(1))",
  "data url link": "[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
  "html comment conditional": "<!--[if IE]><script>alert(1)</script><![endif]-->",
  form: '<form action="https://evil.example"><input name="token"></form>',
  object: '<object data="javascript:alert(1)"></object>',
  "nested obfuscation": "<scr<script>ipt>alert(1)</scr</script>ipt>",
  "attribute breakout in code fence": "```\n</code></pre><script>alert(1)</script>\n```",
};

/** Asserted against the parsed DOM, not the string: escaped text may legitimately read as a payload. */
function inspect(html: string) {
  const document = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  const elements = [...document.body.querySelectorAll("*")];
  return {
    tags: new Set(elements.map((element) => element.tagName.toLowerCase())),
    handlers: elements.flatMap((element) =>
      [...element.attributes].filter((attribute) => attribute.name.startsWith("on")),
    ),
    urls: elements.flatMap((element) =>
      ["href", "src", "data", "action"]
        .map((attribute) => element.getAttribute(attribute))
        .filter((value): value is string => value !== null),
    ),
  };
}

describe("renderMarkdown", () => {
  for (const [name, payload] of Object.entries(PAYLOADS)) {
    it(`neutralises ${name}`, () => {
      const { tags, handlers, urls } = inspect(renderMarkdown(payload));

      for (const forbidden of ["script", "iframe", "style", "object", "embed", "form", "img"]) {
        expect(tags).not.toContain(forbidden);
      }
      expect(handlers).toEqual([]);
      for (const url of urls) {
        expect(url).toMatch(/^(?:https?:|mailto:|#)/i);
      }
    });
  }

  it("renders raw HTML as text rather than dropping it", () => {
    // Silently swallowing it would leave an author wondering why their block vanished.
    expect(renderMarkdown("<b>bold</b>")).toContain("&lt;b&gt;");
  });

  it("keeps the markdown a skill body is actually made of", () => {
    const html = renderMarkdown(
      "# Triage\n\nStart with the [runbook](https://example.com/run).\n\n- one\n- two\n\n`code`\n",
    );

    expect(html).toContain("<h1>Triage</h1>");
    expect(html).toContain('href="https://example.com/run"');
    expect(html).toContain("<li>one</li>");
    expect(html).toContain("<code>code</code>");
  });

  it("allows tables, which skill bodies use for decision matrices", () => {
    const html = renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |\n");

    expect(html).toContain("<table>");
    expect(html).toContain("<td>1</td>");
  });
});
