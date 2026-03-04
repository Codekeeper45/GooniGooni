/**
 * Frontend unit tests for environment.ts
 * Tests detectEnvironment, isLocalModeAvailable, restoreMode, and getAvailableModes.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// We need to mock import.meta.env before importing the module
// Using vi.stubEnv for Vite-aware env mocking

describe("environment utils", () => {
  // Reset module state between tests (singleton cache)
  beforeEach(async () => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  describe("detectEnvironment", () => {
    it("returns local config when VITE_ENVIRONMENT=local", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "local");
      const { detectEnvironment } = await import("../app/utils/environment");
      const config = detectEnvironment();
      expect(config.environment).toBe("local");
      expect(config.isLocalModeAvailable).toBe(true);
      expect(config.isRemoteModeAvailable).toBe(true);
      expect(config.comfyuiUrl).toBeTruthy();
    });

    it("returns production config when VITE_ENVIRONMENT=production", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "production");
      const { detectEnvironment } = await import("../app/utils/environment");
      const config = detectEnvironment();
      expect(config.environment).toBe("production");
      expect(config.isLocalModeAvailable).toBe(false);
      expect(config.isRemoteModeAvailable).toBe(true);
      expect(config.comfyuiUrl).toBeNull();
    });

    it("defaults to local when VITE_ENVIRONMENT is unset", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "");
      const { detectEnvironment } = await import("../app/utils/environment");
      const config = detectEnvironment();
      expect(config.environment).toBe("local");
    });

    it("throws on invalid VITE_ENVIRONMENT value", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "staging");
      const { detectEnvironment } = await import("../app/utils/environment");
      expect(() => detectEnvironment()).toThrow(/Invalid VITE_ENVIRONMENT/);
    });

    it("returns frozen object (FR-015)", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "local");
      const { detectEnvironment } = await import("../app/utils/environment");
      const config = detectEnvironment();
      expect(Object.isFrozen(config)).toBe(true);
    });
  });

  describe("isLocalModeAvailable", () => {
    it("returns true in local environment", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "local");
      const { isLocalModeAvailable } = await import("../app/utils/environment");
      expect(isLocalModeAvailable()).toBe(true);
    });

    it("returns false in production", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "production");
      const { isLocalModeAvailable } = await import("../app/utils/environment");
      expect(isLocalModeAvailable()).toBe(false);
    });
  });

  describe("getAvailableModes", () => {
    it("returns local and remote in local env", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "local");
      const { getAvailableModes } = await import("../app/utils/environment");
      const modes = getAvailableModes();
      expect(modes).toContain("local");
      expect(modes).toContain("remote");
    });

    it("returns only remote in production", async () => {
      vi.stubEnv("VITE_ENVIRONMENT", "production");
      const { getAvailableModes } = await import("../app/utils/environment");
      const modes = getAvailableModes();
      expect(modes).toContain("remote");
      expect(modes).not.toContain("local");
    });
  });

  describe("restoreMode", () => {
    it("returns default mode when sessionStorage is empty", async () => {
      const { restoreMode } = await import("../app/utils/environment");
      const result = restoreMode(["local", "remote"], "local");
      expect(result).toBe("local");
    });

    it("restores valid mode from sessionStorage", async () => {
      sessionStorage.setItem("generation_mode", "remote");
      const { restoreMode } = await import("../app/utils/environment");
      const result = restoreMode(["local", "remote"], "local");
      expect(result).toBe("remote");
      sessionStorage.removeItem("generation_mode");
    });

    it("falls back when stored mode is not in available modes", async () => {
      sessionStorage.setItem("generation_mode", "local");
      const { restoreMode } = await import("../app/utils/environment");
      const result = restoreMode(["remote"], "remote");
      expect(result).toBe("remote");
      sessionStorage.removeItem("generation_mode");
    });
  });
});
