import { useEffect, useState } from "react";
import { api, auth } from "../api";

export default function Consumer() {
  const [verified, setVerified] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);

  useEffect(() => {
    api.get("/verified-loans").then((r) => setVerified(r.items)).catch(() => {});
    api.get("/summary").then(setSummary).catch(() => {});
  }, []);

  const exportCsv = async () => {
    const res = await api.download("/verified-loans/export?format=csv");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "verified-loans.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid" style={{ gap: 18 }}>
      {summary && (
        <div className="grid cols-4">
          <div className="tile"><div className="n">{summary.loans_total}</div><div className="l">Loans</div></div>
          <div className="tile"><div className="n ok">{summary.verified_total}</div><div className="l">Verified</div></div>
          <div className="tile"><div className="n">{summary.exceptions_by_status?.open ?? 0}</div><div className="l">Open exceptions</div></div>
          <div className="tile"><div className="n">{summary.avg_quality_score != null ? Math.round(summary.avg_quality_score * 100) + "%" : "—"}</div><div className="l">Avg quality</div></div>
        </div>
      )}
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Verified records</h2>
          <button className="sm" onClick={exportCsv}>⬇ Export CSV</button>
        </div>
        <table>
          <thead><tr><th>Loan</th><th>Verified by</th><th>Record hash</th><th>Audit</th></tr></thead>
          <tbody>
            {verified.map((v) => (
              <tr key={v.id}>
                <td>{v.loan_id}</td><td>{v.verified_by}</td>
                <td className="muted" style={{ fontFamily: "monospace", fontSize: 12 }}>{v.record_hash?.slice(0, 18)}…</td>
                <td><button className="sm ghost" onClick={() => api.get(`/audit/${v.loan_id}`).then(setAudit)}>View trail</button></td>
              </tr>
            ))}
            {verified.length === 0 && <tr><td colSpan={4} className="muted">No verified records yet.</td></tr>}
          </tbody>
        </table>
      </div>
      {audit && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>Audit trail {audit.chain?.ok ? <span className="badge low" style={{ color: "var(--good)" }}>chain intact ✓</span> : <span className="badge high">chain broken</span>}</h2>
            <button className="sm ghost" onClick={() => setAudit(null)}>Hide</button>
          </div>
          <table>
            <thead><tr><th>#</th><th>Event</th><th>Actor</th><th>When</th></tr></thead>
            <tbody>
              {audit.items.map((e: any) => (
                <tr key={e.id}><td>{e.seq}</td><td>{e.event_type}</td><td>{e.actor}</td><td className="muted">{e.ts_iso?.slice(0, 19)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
