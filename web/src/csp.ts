/**
 * Injected into the built `index.html`. A meta tag because the UI is served as static files by
 * whatever fronts it; a header from that server is strictly better, and this is the floor.
 *
 * `script-src 'self'` with no `unsafe-inline` is the line that matters: a skill body that got a
 * payload past the sanitiser still has nowhere to run it.
 */
export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "font-src 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");
