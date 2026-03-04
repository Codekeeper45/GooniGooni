/**
 * Frontend unit tests for ModeSwitcher component
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

// Mock environment module
vi.mock("../app/utils/environment", () => ({
  getAvailableModes: vi.fn(),
  getDefaultMode: vi.fn(),
}));

import { ModeSwitcher } from "../app/components/ModeSwitcher";
import { getAvailableModes, getDefaultMode } from "../app/utils/environment";

describe("ModeSwitcher", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders both tabs in local environment", () => {
    vi.mocked(getAvailableModes).mockReturnValue(["local", "remote"]);
    vi.mocked(getDefaultMode).mockReturnValue("local");

    const onModeChange = vi.fn();
    render(<ModeSwitcher onModeChange={onModeChange} activeMode="local" />);

    const tabs = screen.getAllByRole("tab");
    expect(tabs.length).toBe(2);
  });

  it("returns null when only one mode is available (production)", () => {
    vi.mocked(getAvailableModes).mockReturnValue(["remote"]);
    vi.mocked(getDefaultMode).mockReturnValue("remote");

    const onModeChange = vi.fn();
    const { container } = render(
      <ModeSwitcher onModeChange={onModeChange} activeMode="remote" />
    );

    expect(container.innerHTML).toBe("");
  });

  it("fires onModeChange callback on tab click", async () => {
    vi.mocked(getAvailableModes).mockReturnValue(["local", "remote"]);
    vi.mocked(getDefaultMode).mockReturnValue("local");

    const onModeChange = vi.fn();
    render(<ModeSwitcher onModeChange={onModeChange} activeMode="local" />);

    const user = userEvent.setup();
    const tabs = screen.getAllByRole("tab");
    // Click the second tab (Remote)
    await user.click(tabs[1]);

    expect(onModeChange).toHaveBeenCalledWith("remote");
  });

  it("sets default mode selection correctly", () => {
    vi.mocked(getAvailableModes).mockReturnValue(["local", "remote"]);
    vi.mocked(getDefaultMode).mockReturnValue("remote");

    const onModeChange = vi.fn();
    render(<ModeSwitcher onModeChange={onModeChange} activeMode="remote" />);

    const tabs = screen.getAllByRole("tab");
    const remoteTab = tabs[1];
    expect(remoteTab).toHaveAttribute("aria-selected", "true");
    expect(remoteTab.textContent).toBe("Remote");
  });
});
