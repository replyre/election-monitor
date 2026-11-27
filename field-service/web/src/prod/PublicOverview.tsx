/** What anyone may see of the field work, with no sign-in: totals from
 * GET /acs/{n}/field/public/summary. No person, note, photo or location is ever shown here. */
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Amount, Num, Pct } from "@/components/Values";

export interface PublicSummary {
  spend: { total: string; entries: number;
    by_bucket: Array<{ code: string; name_en: string; name_hi: string; amount: string; share_pct: string | null }>;
    by_month: Array<{ month: string; amount: string }> };
  reports: { filed: number; open: number; by_status: Array<{ status: string; reports: number }>;
    by_category: Array<{ code: string | null; name_en: string | null; name_hi: string | null; reports: number; open: number }>;
    by_block: Array<{ block_id: string | null; block_en: string | null; block_hi: string | null; reports: number; open: number }> };
  issues: { open: number; closed: number;
    list: Array<{ issue_no: string; title: string; status: string; category_en: string | null; category_hi: string | null;
      block_en: string | null; block_hi: string | null; opened_on: string }> };
}

function Card({ title, empty, children }: { title: string; empty?: boolean; children: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <section className="rounded-ctl border border-line bg-surface p-4">
      <h2 className="mb-2 text-panel font-semibold">{title}</h2>
      {empty ? <p className="text-ink-2">{t("prod.none_yet")}</p> : children}
    </section>
  );
}

export function PublicOverview({ acNumber }: { acNumber: number }) {
  const { t, i18n } = useTranslation();
  const hi = i18n.language === "hi";
  const name = (en: string | null, h: string | null) => (hi ? h || en : en || h) ?? t("prod.unassigned");
  const q = useQuery<PublicSummary>({
    queryKey: ["public-summary", acNumber],
    queryFn: async () => {
      const r = await fetch(`/acs/${acNumber}/field/public/summary`);
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    },
  });
  if (q.isLoading) return <p>{t("prod.loading")}</p>;
  if (q.isError || !q.data) return <p role="alert">{t("prod.load_failed")}</p>;
  const { spend, reports, issues } = q.data;
  const cell = "py-1.5 pr-3";
  return (
    <div className="space-y-4">
      <p className="text-ink-2">{t("prod.public_intro")}</p>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title={t("prod.spend_total")}><div className="text-2xl"><Amount value={spend.total} /></div>
          <p className="text-label text-ink-2">{t("prod.entries", { n: spend.entries })}</p></Card>
        <Card title={t("prod.reports_filed")}><div className="text-2xl"><Num value={reports.filed} /></div>
          <p className="text-label text-ink-2">{t("prod.reports_open", { n: reports.open })}</p></Card>
        <Card title={t("prod.issues_open")}><div className="text-2xl"><Num value={issues.open} /></div>
          <p className="text-label text-ink-2">{t("prod.issues_closed", { n: issues.closed })}</p></Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t("prod.spend_by_bucket")} empty={spend.by_bucket.length === 0}>
          <table className="w-full text-[15px]"><tbody>
            {spend.by_bucket.map((b) => (
              <tr key={b.code} className="border-t border-line">
                <td className={cell}>{name(b.name_en, b.name_hi)}</td>
                <td className={`${cell} text-right`}><Amount value={b.amount} /></td>
                <td className={`${cell} text-right`}><Pct value={b.share_pct} /></td>
              </tr>))}
          </tbody></table>
        </Card>
        <Card title={t("prod.spend_by_month")} empty={spend.by_month.length === 0}>
          <table className="w-full text-[15px]"><tbody>
            {spend.by_month.map((m) => (
              <tr key={m.month} className="border-t border-line">
                <td className={cell}>{m.month}</td>
                <td className={`${cell} text-right`}><Amount value={m.amount} /></td>
              </tr>))}
          </tbody></table>
        </Card>
        <Card title={t("prod.reports_by_category")} empty={reports.by_category.length === 0}>
          <table className="w-full text-[15px]"><tbody>
            {reports.by_category.map((c) => (
              <tr key={c.code ?? "none"} className="border-t border-line">
                <td className={cell}>{name(c.name_en, c.name_hi)}</td>
                <td className={`${cell} text-right`}><Num value={c.reports} /></td>
                <td className={`${cell} text-right text-ink-2`}>{t("prod.open_n", { n: c.open })}</td>
              </tr>))}
          </tbody></table>
        </Card>
        <Card title={t("prod.reports_by_block")} empty={reports.by_block.length === 0}>
          <table className="w-full text-[15px]"><tbody>
            {reports.by_block.map((b) => (
              <tr key={b.block_id ?? "none"} className="border-t border-line">
                <td className={cell}>{name(b.block_en, b.block_hi)}</td>
                <td className={`${cell} text-right`}><Num value={b.reports} /></td>
                <td className={`${cell} text-right text-ink-2`}>{t("prod.open_n", { n: b.open })}</td>
              </tr>))}
          </tbody></table>
        </Card>
      </div>
      <Card title={t("prod.issue_list")} empty={issues.list.length === 0}>
        <table className="w-full text-[15px]"><tbody>
          {issues.list.map((i) => (
            <tr key={i.issue_no} className="border-t border-line">
              <td className={cell}>{i.issue_no}</td>
              <td className={cell}>{i.title}</td>
              <td className={cell}>{name(i.category_en, i.category_hi)}</td>
              <td className={cell}>{name(i.block_en, i.block_hi)}</td>
              <td className={cell}>{t(`issue_status.${i.status}`)}</td>
              <td className={cell}>{i.opened_on}</td>
            </tr>))}
        </tbody></table>
      </Card>
    </div>
  );
}

