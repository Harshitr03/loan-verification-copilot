import { useEffect, useState } from "react";
import { api } from "../api";

function Badge({ s }: { s: string }) { return <span className={"badge " + s}>{s}</span>; }

export default function Reviewer() {
  const [items, setItems] = useState<any[]>([]);
  const [sev, setSev] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<any>(null);

  const load = () => {
    const p = new URLSearchParams();
    if (sev) p.set("severity", sev);
    if (status) p.set("status", status);
    if (q) p.set("q", q);
    api.get("/exceptions?" + p.toString()).then((r) => setItems(r.items)).catch(() => {});
  };
  useEffect(() => { load(); }, [sev, status, q]);

  return (
    <div className="card">
      <h2>Exception queue</h2>
      <div className="row" style={{ marginBottom: 12 }}>
        <select value={sev} onChange={(e) => setSev(e.target.value)}>
          <option value="">All severities</option><option>low</option><option>medium</option><option>high</option><option>critical</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option><option>open</option><option>accepted</option><option>resolved</option><option>rejected</option>
        </select>
        <input placeholder="search loan id…" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="muted">{items.length} shown</span>
      </div>
      <table>
        <thead><tr><th>Loan</th><th>Rule</th><th>Field</th><th>Observed</th><th>Expected</th><th>Severity</th><th>Status</th></tr></thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id} className="click" onClick={() => setOpen(e)}>
              <td>{e.loan_id}</td><td>{e.rule_id}</td><td>{e.field}</td>
              <td>{e.observed_value}</td><td>{e.expected}</td>
              <td><Badge s={e.severity} /></td><td>{e.status}</td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={7} className="muted">No exceptions.</td></tr>}
        </tbody>
      </table>
      {open && <Drawer exc={open} onClose={() => { setOpen(null); load(); }} />}
    </div>
  );
}

function Drawer({ exc, onClose }: { exc: any; onClose: () => void }) {
  const [ai, setAi] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => { api.get(`/loans/${exc.loan_id}`).then(setDetail).catch(() => {}); }, [exc.loan_id]);

  const runAi = async (kind: string) => {
    setMsg("");
    try { setAi(await api.post(`/exceptions/${exc.id}/ai`, { kind })); }
    catch (e: any) { setMsg(e.message); }
  };
  const decide = async (decision: string) => {
    if (ai?.id) await api.post(`/ai/${ai.id}/decision`, { decision });
    setMsg(`AI ${decision}`);
  };
  const resolve = async (action: string) => {
    try {
      const body: any = { action };
      if (action === "edit") { body.field = exc.field; body.new_value = ai?.suggested_value ?? prompt("New value?") ?? ""; }
      await api.post(`/exceptions/${exc.id}/resolve`, body);
      setMsg(`Exception ${action}ed`);
    } catch (e: any) { setMsg(e.message); }
  };
  const verify = async () => {
    try { const r = await api.post(`/loans/${exc.loan_id}/verify`); setMsg("Verified · hash " + r.record_hash.slice(0, 12) + "…"); }
    catch (e: any) { setMsg(e.message); }
  };

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="drawer">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Loan {exc.loan_id}</h2>
          <button className="ghost sm" onClick={onClose}>Close</button>
        </div>
        <p className="muted">{exc.rule_id} · {exc.message}</p>
        <div className="ai" style={{ marginTop: 4 }}>
          <div><b>{exc.field}</b> = {exc.observed_value}</div>
          <div className="muted">expected {exc.expected}{exc.sibling_value ? ` · servicer ${exc.sibling_value}` : ""}</div>
        </div>

        <h2 style={{ marginTop: 18 }}>AI assistant</h2>
        <div className="row">
          <button className="sm" onClick={() => runAi("explain")}>Explain</button>
          <button className="sm" onClick={() => runAi("suggest")}>Suggest</button>
          <button className="sm" onClick={() => runAi("compare")}>Compare</button>
        </div>
        {ai && (
          <div className="ai">
            <div className="muted" style={{ fontSize: 11 }}>{ai.provider} · {ai.model} · confidence {ai.confidence}</div>
            <div style={{ marginTop: 4 }}>{ai.response}</div>
            {ai.suggested_value && <div style={{ marginTop: 6 }}>→ suggested: <b>{ai.suggested_value}</b></div>}
            <div className="row" style={{ marginTop: 8 }}>
              <button className="sm ghost" onClick={() => decide("accepted")}>Accept</button>
              <button className="sm ghost" onClick={() => decide("rejected")}>Reject</button>
            </div>
          </div>
        )}

        <h2 style={{ marginTop: 18 }}>Decision</h2>
        <div className="row">
          <button className="sm" onClick={() => resolve("edit")}>Apply edit</button>
          <button className="sm ghost" onClick={() => resolve("approve")}>Approve</button>
          <button className="sm ghost" onClick={() => resolve("reject")}>Reject</button>
          <button className="sm ghost" onClick={() => resolve("request_correction")}>Request fix</button>
        </div>
        <div style={{ marginTop: 12 }}>
          <button onClick={verify}>✓ Verify loan</button>
        </div>
        {msg && <p className="ok" style={{ marginTop: 10 }}>{msg}</p>}

        {detail && (
          <>
            <h2 style={{ marginTop: 18 }}>All exceptions ({detail.exceptions.length})</h2>
            {detail.exceptions.map((e: any) => (
              <div key={e.id} className="muted" style={{ fontSize: 12 }}>{e.rule_id} · {e.field} · {e.status}</div>
            ))}
          </>
        )}
      </div>
    </>
  );
}
