import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

beforeEach(() => {
  if (typeof window !== "undefined" && window.sessionStorage) {
    window.sessionStorage.clear();
  }
});

afterEach(() => {
  cleanup();
});
