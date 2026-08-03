import DOMPurify from "dompurify";
import { Marked } from "marked";

/**
 * Skill bodies are attacker-influenced: anyone who can publish can put anything in a `SKILL.md`,
 * and the reader may be an admin who can publish to every agent in the organization. So the
 * markdown pipeline is told not to emit raw HTML, and the result is sanitised anyway. Either
 * alone would be enough today; the pair survives one of them being reconfigured.
 */
const ALLOWED_TAGS = [
  "p",
  "br",
  "hr",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "strong",
  "em",
  "del",
  "code",
  "pre",
  "blockquote",
  "ul",
  "ol",
  "li",
  "a",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
];

function escape(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Raw HTML is shown as the text it is, rather than dropped, so an author can see what happened. */
const parser = new Marked({ gfm: true, breaks: false, async: false }).use({
  renderer: { html: ({ text }) => escape(text) },
});

export function renderMarkdown(source: string): string {
  const html = parser.parse(source, { async: false });
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: ["href", "title"],
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|#)/i,
    FORBID_TAGS: ["style", "script", "iframe", "object", "embed", "form"],
    FORBID_ATTR: ["style", "srcset"],
  });
}
