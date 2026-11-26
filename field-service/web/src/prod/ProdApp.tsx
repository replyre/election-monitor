/** Production composition. There is no sign-in page: visitors see the public totals; on the admin
 * address the Cloudflare Access sign-in is traded for a token (shared with the core app) and the full
 * field screens open, each still limited by the member's scope. */
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { SessionContext, type Session } from "@/lib/session";
import { FieldRoutes } from "@/field/routes";
import { ProdShell } from "./ProdShell";
import { PublicOverview } from "./PublicOverview";
import { exchangeAccess, fetchConfig, getToken, onAdminHost, pickAc, setToken, type SiteConfig } from "./site";

interface Me {
  user: { user_id: string; display_name: string; role: string };
  ac: { ac_number: number; name_hi: string; name_en: string };
  member: { member_id: string; display_name: string; is_principal: boolean; is_coordinator: boolean;
    finance_scope: Session["financeScope"] } | null;
}

type State =
  | { kind: "loading" }
  | { kind: "failed"; message: string; adminHost: boolean }
  | { kind: "public"; config: SiteConfig; ac: number }
  | { kind: "admin"; config: SiteConfig; session: Session };

async function sessionFor(token: string, ac: number): Promise<Session | null> {
  const r = await fetch(`/acs/${ac}/field/me`, { headers: { Authorization: `Bearer ${token}` } });
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(`me ${r.status}`);
  const me = (await r.json()) as Me;
  return {
    token, acNumber: me.ac.ac_number, acName: { name_hi: me.ac.name_hi, name_en: me.ac.name_en },
    userId: me.user.user_id, userName: me.member?.display_name ?? me.user.display_name, role: me.user.role,
    financeScope: me.member?.finance_scope ?? null, memberId: me.member?.member_id ?? null,
    isPrincipal: !!me.member?.is_principal, isCoordinator: !!me.member?.is_coordinator,
  };
}

export function ProdApp() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    let admin = false;
    (async () => {
      try {
        const config = await fetchConfig();
        admin = onAdminHost(config);
        const ac = pickAc(config);
        if (ac === null) throw new Error(t("prod.no_ac"));
        if (!admin) {
          setToken(null);                      // the public site never acts as anyone
          if (live) setState({ kind: "public", config, ac });
          return;
        }
        let session = getToken() ? await sessionFor(getToken()!, ac) : null;
        if (!session) session = await sessionFor(await exchangeAccess(), ac);   // expired or first visit
        if (!session) throw new Error(t("prod.no_access"));
        qc.clear();
        if (live) setState({ kind: "admin", config, session });
      } catch (e) {
        if (live) setState({ kind: "failed", message: e instanceof Error ? e.message : String(e), adminHost: admin });
      }
    })();
    return () => { live = false; };
  }, [qc, t]);

  if (state.kind === "loading") return <p className="p-4">{t("prod.loading")}</p>;
  if (state.kind === "failed") {
    return (
      <ProdShell session={null} adminUrl={null} adminHost={state.adminHost}>
        <p role="alert">{state.message}</p>
      </ProdShell>
    );
  }
  if (state.kind === "public") {
    return (
      <ProdShell session={null} adminUrl={state.config.admin_url} adminHost={false}>
        <Routes>
          <Route path="/field" element={<PublicOverview acNumber={state.ac} />} />
          <Route path="*" element={<Navigate to="/field" replace />} />
        </Routes>
      </ProdShell>
    );
  }
  return (
    <SessionContext.Provider value={state.session}>
      <ProdShell session={state.session} adminUrl={state.config.admin_url} adminHost>
        <FieldRoutes />
      </ProdShell>
    </SessionContext.Provider>
  );
}
