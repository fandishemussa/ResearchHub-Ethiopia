import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "./page";
import { api } from "@/lib/api";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    login: vi.fn(),
    currentUser: vi.fn(),
  },
}));

describe("LoginPage", () => {
  beforeEach(() => {
    replace.mockReset();
    refresh.mockReset();
    vi.mocked(api.login).mockResolvedValue({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
      expires_at: "2026-07-16T00:00:00Z",
    });
    vi.mocked(api.currentUser).mockResolvedValue({
      id: "user-1",
      email: "admin@example.edu",
      username: "admin",
      full_name: "Administrator",
      is_active: true,
      is_verified: true,
      is_suspended: false,
      university_id: null,
      faculty_id: null,
      department_id: null,
      last_login_at: null,
      created_at: "2026-07-16T00:00:00Z",
      roles: ["PLATFORM_ADMIN"],
      permissions: [],
    });
  });

  it("submits accessible credentials and redirects after validation", async () => {
    render(<LoginPage />);
    await userEvent.type(
      screen.getByRole("textbox", { name: /email or username/i }),
      "admin",
    );
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "correct horse battery staple" },
    });
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(api.login).toHaveBeenCalledWith(
        "admin",
        "correct horse battery staple",
      ),
    );
    expect(api.currentUser).toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("renders a friendly error without exposing internals", async () => {
    vi.mocked(api.login).mockRejectedValue(new Error("backend stack"));
    render(<LoginPage />);
    await userEvent.type(
      screen.getByRole("textbox", { name: /email or username/i }),
      "admin",
    );
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: "wrong password" },
    });
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sign in could not be completed",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("backend stack");
  });
});
