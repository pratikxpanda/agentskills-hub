import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest is not running with globals, so Testing Library's automatic cleanup never registers.
afterEach(cleanup);
