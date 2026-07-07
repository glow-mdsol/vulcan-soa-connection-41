import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { logout } from "./api/client";
import App from "./App";

vi.mock("./routes", () => ({
  default: () => <p>Routes go here</p>,
}));

vi.mock("./api/client", () => ({
  logout: vi.fn(),
}));

describe("App", () => {
  beforeEach(() => {
    vi.mocked(logout).mockReset();
    vi.mocked(logout).mockResolvedValue();
  });

  it("renders the app header", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Vulcan Schedule of Activities" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
    expect(screen.getByText("Routes go here")).toBeInTheDocument();
  });

  it("logs out and redirects home", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      value: { assign },
      writable: true,
      configurable: true,
    });

    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(logout).toHaveBeenCalledTimes(1);
    expect(assign).toHaveBeenCalledWith("/");
  });
});
