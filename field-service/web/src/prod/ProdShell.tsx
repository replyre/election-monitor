/** The production header around the field pages: back to the main app, the field pages this user may
 * open, language, theme, and the admin link (or Cloudflare Access's sign-out on the admin site). */
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { setLang } from "@/i18n";
import { useTheme } from "@/lib/theme";
import type { Session } from "@/lib/session";
import { FIELD_PAGES } from "@/field/nav";

export function ProdShell({ session, adminUrl, adminHost, children }: {
  session: Session | null; adminUrl: string | null; adminHost: boolean; children: React.ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const { theme, toggle } = useTheme();
  const pages = session ? FIELD_PAGES.filter((p) => p.visible(session)) : [];
  const link = "rounded-ctl px-2.5 py-2 text-[15px] text-ink-2 hover:text-ink";
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-[1000] border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-2 px-4 py-2">
          <a href="/" className="font-semibold">{t("prod.main_app")}</a>
          <nav aria-label={t("shell.nav")} className="flex flex-wrap items-center gap-0.5">
            <NavLink to="/field" end className={link}>{t("prod.field_home")}</NavLink>
            {pages.map((p) => (
              <NavLink key={p.path} to={p.path} className={link}>{t(p.key)}</NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1.5">
            <button type="button" className={link} onClick={() => setLang(i18n.language === "hi" ? "en" : "hi")}>
              {i18n.language === "hi" ? "English" : "हिन्दी"}
            </button>
            <button type="button" className={link} onClick={toggle}>
              {theme === "dark" ? t("shell.to_light") : t("shell.to_dark")}
            </button>
            {session && <span className="rounded-ctl border border-line px-2 py-1 text-label">{session.userName}</span>}
            {adminHost
              ? <a className={link} href="/cdn-cgi/access/logout">{t("prod.sign_out")}</a>
              : adminUrl && <a className={link} href={`${adminUrl}/field/`}>{t("prod.admin")}</a>}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-4">{children}</main>
    </div>
  );
}
