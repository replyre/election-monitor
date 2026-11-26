/** The production site around the field pages: the core app's /config, its admin sign-in and its
 * token. The field screens live at /field/ on the same origin as the core app, so the admin token the
 * core app stores ("giridih.token") is the one these screens send to the field API. */

export const TOKEN_KEY = "giridih.token";
const AC_KEY = "giridih.ac";

export interface SiteConfig {
  acs: Array<{ ac_number: number; name_en: string; name_hi: string }>;
  default_ac: number | null;
  admin_url: string | null;
}

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* private mode: the session simply does not persist */ }
}

/** The constituency: ?ac= first, then the one last picked in the core app, then the default. */
export function pickAc(config: SiteConfig): number | null {
  const known = new Set(config.acs.map((a) => a.ac_number));
  const fromUrl = Number(new URLSearchParams(window.location.search).get("ac"));
  if (known.has(fromUrl)) return fromUrl;
  try {
    const saved = Number(localStorage.getItem(AC_KEY));
    if (known.has(saved)) return saved;
  } catch { /* ignore */ }
  return config.default_ac ?? config.acs[0]?.ac_number ?? null;
}

export function onAdminHost(config: SiteConfig): boolean {
  if (!config.admin_url) return false;
  try { return new URL(config.admin_url).origin === window.location.origin; } catch { return false; }
}

export async function fetchConfig(): Promise<SiteConfig> {
  const r = await fetch("/api/config");
  if (!r.ok) throw new Error(`config ${r.status}`);
  return r.json() as Promise<SiteConfig>;
}

/** Cloudflare Access has checked the email at the edge; the core trades that for an admin token. */
export async function exchangeAccess(): Promise<string> {
  const r = await fetch("/api/auth/access", { method: "POST" });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  const { access_token } = (await r.json()) as { access_token: string };
  setToken(access_token);
  return access_token;
}
