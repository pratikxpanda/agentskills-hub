import type { ApiError } from "../api/client";
import { renderMarkdown } from "../markdown";

export function Failure({ error }: { error: ApiError }) {
  return (
    <div className="failure" role="alert">
      <p>{error.message}</p>
      {error.details.length > 0 && (
        <ul>
          {error.details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      )}
      <p className="code">{error.code}</p>
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted">Loading {what}…</p>;
}

export function Tags({ tags, onSelect }: { tags: string[]; onSelect?: (tag: string) => void }) {
  return (
    <ul className="tags">
      {tags.map((tag) => (
        <li key={tag}>
          {onSelect ? (
            <button type="button" onClick={() => onSelect(tag)}>
              {tag}
            </button>
          ) : (
            tag
          )}
        </li>
      ))}
    </ul>
  );
}

export function Markdown({ source }: { source: string }) {
  // The only `dangerouslySetInnerHTML` in the app, and its input has been through `renderMarkdown`
  // — raw HTML escaped by the parser, then sanitised. See src/markdown.ts.
  return (
    <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(source) }} />
  );
}

export function Copyable({ label, value }: { label: string; value: string }) {
  return (
    <div className="copyable">
      <label>
        <span>{label}</span>
        <input readOnly value={value} onFocus={(event) => event.target.select()} />
      </label>
      <button type="button" onClick={() => void navigator.clipboard?.writeText(value)}>
        Copy
      </button>
    </div>
  );
}
