/**
 * Frontend unit tests for apiFactory
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

describe("apiFactory", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("getAPIClient('remote') returns RemoteGenerationClient", async () => {
    const { getAPIClient } = await import("../app/api/apiFactory");
    const client = await getAPIClient("remote");
    expect(client).toBeDefined();
    expect(typeof client.generate).toBe("function");
    expect(typeof client.cancelGeneration).toBe("function");
    expect(typeof client.onProgress).toBe("function");
    expect(typeof client.checkAvailability).toBe("function");
  });

  it("getAPIClient('local') returns ComfyUIClient in dev", async () => {
    // import.meta.env.DEV is true in test mode (vitest)
    const { getAPIClient } = await import("../app/api/apiFactory");
    const client = await getAPIClient("local");
    expect(client).toBeDefined();
    expect(typeof client.generate).toBe("function");
    expect(typeof client.cancelGeneration).toBe("function");
  });

  it("registerRemoteClient sets a custom remote client", async () => {
    const { registerRemoteClient, getAPIClient } = await import("../app/api/apiFactory");

    const mockClient = {
      generate: vi.fn(),
      cancelGeneration: vi.fn(),
      onProgress: vi.fn(),
      checkAvailability: vi.fn(),
    };

    registerRemoteClient(mockClient);
    const client = await getAPIClient("remote");
    expect(client).toBe(mockClient);
  });

  it("throws on unknown mode", async () => {
    const { getAPIClient } = await import("../app/api/apiFactory");
    await expect(getAPIClient("unknown" as any)).rejects.toThrow(/Unknown generation mode/);
  });
});
