import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

// jsdom implements neither of these, and the shell uses both for image
// evidence. Without them an unrelated evidence fetch throws inside a test that
// is checking something else entirely.
if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = () => "blob:evidence";
  URL.revokeObjectURL = () => undefined;
}
