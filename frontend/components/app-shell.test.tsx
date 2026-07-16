import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";
import { api } from "@/lib/api";
import { storeAuthTokens } from "@/lib/auth";

const { replace, refresh } = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
}));
const router = { replace, refresh };

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => router,
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light", setTheme: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    currentUser: vi.fn(),
    logout: vi.fn(),
  },
}));

describe("AppShell authentication guard", () => {
  beforeEach(() => {
    sessionStorage.clear();
    replace.mockReset();
    refresh.mockReset();
    vi.mocked(api.currentUser).mockReset();
  });

  it("redirects an anonymous visitor without rendering protected content", async () => {
    render(
      <AppShell>
        <div>Private dashboard content</div>
      </AppShell>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(
      screen.queryByText("Private dashboard content"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Redirecting to sign in…")).toBeInTheDocument();
    expect(api.currentUser).not.toHaveBeenCalled();
  });

  it("renders the application only after the stored session is validated", async () => {
    storeAuthTokens({
      access_token: "access",
      refresh_token: "refresh",
      token_type: "bearer",
      expires_at: "2026-07-17T00:00:00Z",
    });
    vi.mocked(api.currentUser).mockResolvedValue({
      id: "user-1",
      email: "reader@example.edu",
      username: "reader",
      full_name: "Research Reader",
      is_active: true,
      is_verified: true,
      is_suspended: false,
      university_id: null,
      faculty_id: null,
      department_id: null,
      last_login_at: null,
      created_at: "2026-07-16T00:00:00Z",
      roles: ["PUBLIC_USER"],
      permissions: ["publications.read"],
    });

    render(
      <AppShell>
        <div>Private dashboard content</div>
      </AppShell>,
    );

    expect(
      screen.queryByText("Private dashboard content"),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByText("Private dashboard content"),
    ).toBeInTheDocument();
    expect(api.currentUser).toHaveBeenCalledTimes(1);
    expect(replace).not.toHaveBeenCalledWith("/login");
  });
});
