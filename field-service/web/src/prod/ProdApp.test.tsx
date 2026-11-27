import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@/lib/theme";
import { ProdApp } from "./ProdApp";
import { setLang } from "@/i18n";

const SUMMARY = {
  spend: { total: "1500.00", entries: 2, by_bucket: [{ code: "FOOD", name_en: "Food", name_hi: "भोजन", amount: "1500.00", share_pct: "100.00" }],
    by_month: [{ month: "2026-11", amount: "1500.00" }] },
  reports: { filed: 2, open: 1, by_status: [], by_category: [], by_block: [] },
  issues: { open: 1, closed: 0, list: [{ issue_no: "32-I-000001", title: "Hand pump broken", status: "open",
    category_en: "Health", category_hi: "स्वास्थ्य", block_en: "Block A", block_hi: "प्रखंड क", opened_on: "2026-11-20" }] },
};
const ME = { user: { user_id: "7", display_name: "Admin One", role: "admin" },
  ac: { ac_number: 32, name_hi: "गिरिडीह", name_en: "Giridih" }, member: null };

type Route = (init?: RequestInit) => { status?: number; body: unknown };

function serve(routes: Record<string, Route>) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const key = `${(init?.method ?? "GET").toUpperCase()} ${path}`;
    calls.push(key);
    const route = routes[key];
    const out = route ? route(init) : { status: 404, body: { detail: "no route" } };
    return new Response(JSON.stringify(out.body), { status: out.status ?? 200,
      headers: { "Content-Type": "application/json" } });
  }));
  return calls;
}

const config = (adminUrl: string | null) => () => ({
  body: { acs: [{ ac_number: 32, name_en: "Giridih", name_hi: "गिरिडीह" }], default_ac: 32, admin_url: adminUrl } });

function mount() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ThemeProvider><MemoryRouter initialEntries={["/field"]}><ProdApp /></MemoryRouter></ThemeProvider>
    </QueryClientProvider>);
}

beforeEach(() => { localStorage.clear(); setLang("en"); });
afterEach(() => vi.unstubAllGlobals());

describe("ProdApp", () => {
  it("shows visitors the public totals with no sign-in and sends no token", async () => {
    localStorage.setItem("giridih.token", "left-over");
    const calls = serve({
      "GET /api/config": config("https://admin.example.org"),
      "GET /acs/32/field/public/summary": () => ({ body: SUMMARY }),
    });
    mount();
    expect(await screen.findByText("Hand pump broken")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute("href", "https://admin.example.org/field/");
    expect(screen.queryByRole("link", { name: "Sign out" })).not.toBeInTheDocument();
    expect(localStorage.getItem("giridih.token")).toBeNull();
    expect(calls).not.toContain("POST /api/auth/access");
    expect(calls.some((c) => c.endsWith("/field/me"))).toBe(false);
  });

  it("signs an admin in on the admin address and opens the field screens", async () => {
    const calls = serve({
      "GET /api/config": config(window.location.origin),
      "POST /api/auth/access": () => ({ body: { access_token: "admin-tok" } }),
      "GET /acs/32/field/me": (init) => (new Headers(init?.headers).get("Authorization") === "Bearer admin-tok"
        ? { body: ME } : { status: 401, body: {} }),
    });
    mount();
    expect(await screen.findByText("Admin One")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign out" })).toHaveAttribute("href", "/cdn-cgi/access/logout");
    expect(localStorage.getItem("giridih.token")).toBe("admin-tok");
    expect(calls.filter((c) => c === "POST /api/auth/access")).toHaveLength(1);
  });

  it("exchanges again when the stored admin token has expired", async () => {
    localStorage.setItem("giridih.token", "stale");
    serve({
      "GET /api/config": config(window.location.origin),
      "POST /api/auth/access": () => ({ body: { access_token: "fresh" } }),
      "GET /acs/32/field/me": (init) => (new Headers(init?.headers).get("Authorization") === "Bearer fresh"
        ? { body: ME } : { status: 401, body: {} }),
    });
    mount();
    await waitFor(() => expect(localStorage.getItem("giridih.token")).toBe("fresh"));
    expect(await screen.findByText("Admin One")).toBeInTheDocument();
  });

  it("explains a refused email instead of showing a form", async () => {
    serve({
      "GET /api/config": config(window.location.origin),
      "POST /api/auth/access": () => ({ status: 403, body: { detail: "This email does not have admin access" } }),
    });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("This email does not have admin access");
    expect(screen.getByRole("link", { name: "Sign out" })).toBeInTheDocument();
  });
});

describe("PublicOverview", () => {
  it("says so when there is nothing yet instead of showing empty boxes", async () => {
    const empty = { spend: { total: "0.00", entries: 0, by_bucket: [], by_month: [] },
      reports: { filed: 0, open: 0, by_status: [], by_category: [], by_block: [] },
      issues: { open: 0, closed: 0, list: [] } };
    serve({
      "GET /api/config": config(null),
      "GET /acs/32/field/public/summary": () => ({ body: empty }),
    });
    mount();
    expect(await screen.findAllByText("Nothing yet.")).toHaveLength(5);
  });
});
