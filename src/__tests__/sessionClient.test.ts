/**
 * Frontend unit tests for sessionClient URL normalization.
 *
 * @vitest-environment jsdom
 */

import { describe, expect, it } from "vitest";

import { resolveMediaUrl } from "../app/utils/sessionClient";

describe("resolveMediaUrl", () => {
  it("removes api_key from modal result URL and rewrites to /api route", () => {
    const url = resolveMediaUrl(
      "https://workspace-a--gooni-api.modal.run/results/task-1?api_key=secret123&foo=1",
      "/results/workspace-a::task-1",
    );
    expect(url).toBe("/api/results/workspace-a::task-1?foo=1");
    expect(url.includes("api_key=")).toBe(false);
  });

  it("removes api_key from relative preview URL", () => {
    const url = resolveMediaUrl(
      "/preview/workspace-a::task-2?api_key=secret123",
      "/preview/workspace-a::task-2",
    );
    expect(url).toBe("/api/preview/workspace-a::task-2");
    expect(url.includes("api_key=")).toBe(false);
  });
});

