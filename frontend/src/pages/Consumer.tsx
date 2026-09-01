import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, Hash, SkeletonRows, useToast } from "../ui";

export default function Consumer() {
  const [verified, setVerified] = useState<any[] | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);
  const [auditFor, setAuditFor] = useState<string>("");
  const toast = useToast();

  useEffect(() => {
    api.get("/verified-loans").then((r) => setVerified(r.items)).catch(() => setVerified([]));
    api.get("/summary").then(setSummary).catch(() => {});
  }, []);

  const exportCsv = async () => {
    try {
      const res = await api.download("/verified-loans/export?format=csv");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "verified-loans.csv"; a.click();
      URL.revokeObjectURL(url);
      toast("Exported verified-loans.csv");
    } catch (e: any) { toast("Export failed — " + e.message, "err"); }
  };

  const showAudit = (loanId: string) => {
    setAuditFor(loanId); setAudit(null);
    api.get(`/audit/${loanId}`).then(setAudit).catch((e) => toast(e.message, "err"));
  };

  const q = summary?.avg_quality_score != null ? Math.round(summary.avg_quality_score * 100) + "%" : "—";

  return (
    <div className="grid" style={{ gap: 20 }}>
      {summary && (
        <div className="grid cols-4">
          <div className="tile accent"><span className="n">{summary.loans_total}</span><div className="l">Loans</div></div>
          <div className="tile good"><span className="n ok">{summary.verified_total}</span><div className="l">Verified</div></div>
          <div className="tile warn"><span className="n" style={{ color: "var(--warn)" }}>{summary.exceptions_by_status?.open ?? 0}</span><div className="l">Open exceptions</div></div>
          <div className="tile"><span className="n">{q}</span><div className="l">Avg quality</div></div>
        </div>
      )}

      <div>
        <div className="eyebrow"><span className="idx">§</span> Registry</div>
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}>Verified records</h2>
            <button className="sm ghost" onClick={exportCsv}>↓ Export CSV</button>
          </div>
          <table>
            <thead><tr><th>Loan</th><th>Verified by</th><th>Record hash</th><th></th></tr></thead>
            <tbody>
              {verified === null && <SkeletonRows cols={4} />}
              {verified?.map((v) => (
                <tr key={v.id}>
                  <td className="cell-strong">{v.loan_id}</td>
                  <td className="mono muted">{v.verified_by}</td>
                  <td><Hash value={v.record_hash} len={18} /></td>
                  <td style={{ textAlign: "right" }}>
                    <button className="sm ghost" onClick={() => showAudit(v.loan_id)}>View trail</button>
                  </td>
                </tr>
              ))}
              {verified?.length === 0 && (
                <tr><td colSpan={4}><Empty icon="✓" title="No verified records yet"
                  hint="Once a reviewer verifies a loan, its sealed record appears here." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {auditFor && (
        <div>
          <div className="eyebrow"><span className="idx">#</span> Provenance</div>
          <div className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
              <h2 style={{ margin: 0 }}>
                Audit trail · <span className="mono" style={{ textTransform: "none" }}>{auditFor}</span>
              </h2>
              <div className="row">
                {audit && (audit.chain?.ok
                  ? <span className="seal-badge intact">✓ Chain intact</span>
                  : <span className="seal-badge broken">✕ Chain broken</span>)}
                <button className="sm ghost" onClick={() => { setAudit(null); setAuditFor(""); }}>Hide</button>
              </div>
            </div>
            {!audit ? (
              <div className="skel" style={{ height: 80 }} />
            ) : (
              <ol className="chain">
                {audit.items.map((e: any) => (
                  <li key={e.id}>
                    <span className="node">{e.seq}</span>
                    <div className="link-row">
                      <div className="ev">{e.event_type}</div>
                      <div className="meta">{e.actor} · {e.ts_iso?.slice(0, 19).replace("T", " ")}</div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {audit && (
              <p className="faint mono" style={{ fontSize: 11, marginBottom: 0 }}>
                Each entry is hash-linked to the one before it — altering any record breaks the chain.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
