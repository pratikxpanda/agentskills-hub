import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { CONTENT_SECURITY_POLICY } from "../csp";

const directives = new Map(
  CONTENT_SECURITY_POLICY.split("; ").map((directive) => {
    const [name, ...values] = directive.split(" ");
    return [name ?? "", values.join(" ")];
  }),
);

describe("content security policy", () => {
  it("forbids inline and remote script", () => {
    // The compensating control if a payload ever survives the sanitiser: nowhere to run.
    expect(directives.get("script-src")).toBe("'self'");
    expect(CONTENT_SECURITY_POLICY).not.toContain("unsafe-inline");
    expect(CONTENT_SECURITY_POLICY).not.toContain("unsafe-eval");
    expect(CONTENT_SECURITY_POLICY).not.toContain("*");
  });

  it("closes the exits a stored payload would use", () => {
    expect(directives.get("object-src")).toBe("'none'");
    expect(directives.get("base-uri")).toBe("'none'");
    expect(directives.get("form-action")).toBe("'none'");
    expect(directives.get("frame-ancestors")).toBe("'none'");
    expect(directives.get("default-src")).toBe("'self'");
  });

  it("has no inline script in the page the policy applies to", () => {
    const html = readFileSync("index.html", "utf8");

    expect(html).not.toMatch(/<script(?![^>]*\bsrc=)/i);
    expect(html).not.toMatch(/\son\w+\s*=/i);
  });
});
