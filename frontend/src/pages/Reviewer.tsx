import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SkeletonRows, useToast } from "../ui";

function Badge({ s }: { s: string }) { return <span className={"badge " + s}>{s}</span>; }

export default function Reviewer() {
  const [items, setItems] = useState<any[] | null>(null);
  const [sev, setSev] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<any>(null);

  const load = () => {
    const p = new URLSearchParams();
    if (sev) p.set("severity", sev);
    if (status) p.set("status", status);
    if (q) p.set("q", q);
    setItems(null);
    api.get("/exceptions?" + p.toString()).then((r) => setItems(r.items)).catch(() => setItems([]));
  };
  useEffect(() => { load(); }, [sev, status, q]);

  return (
    <div>
      <div className="eyebrow"><span className="idx">◇</span> Exception queue</div>
      <div className="card">
        <div className="row" style={{ marginBottom: 14, justifyContent: "space-between" }}>
          <div className="row">
            <select value={sev} onChange={(e) => setSev(e.target.value)} aria-label="Severity filter">
              <option value="">All severities</option><option>low</option><option>medium</option><option>high</option><option>critical</option>
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
              <option value="">All statuses</option><option>open</option><option>accepted</option><option>resolved</option><option>rejected</option>
            </select>
            <input placeholder="search loan id…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <span className="faint mono" style={{ fontSize: 12 }}>{items?.length ?? "…"} shown</span>
        </div>
        <table>
          <thead><tr><th>Loan</th><th>Rule</th><th>Field</th><th>Observed</th><th>Expected</th><th>Severity</th><th>Status</th></tr></thead>
          <tbody>
            {items === null && <SkeletonRows cols={7} />}
            {items?.map((e) => (
              <tr key={e.id} className="click" onClick={() => setOpen(e)}>
                <td className="cell-strong">{e.loan_id}</td>
                <td className="mono">{e.rule_id}</td>
                <td className="mono">{e.field}</td>
                <td>{e.observed_value}</td><td className="muted">{e.expected}</td>
                <td><Badge s={e.severity} /></td>
                <td><span className={"pill " + e.status}>{e.status}</span></td>
              </tr>
            ))}
            {items?.length === 0 && (
              <tr><td colSpan={7}><Empty icon="◇" title="Queue clear"
                hint="No exceptions match these filters. Adjust severity or status to see more." /></td></tr>
            )}
          </tbody>
        </table>
      </div>
      {open && <Drawer exc={open} onClose={() => { setOpen(null); load(); }} />}
    </div>
  );
}

function Drawer({ exc, onClose }: { exc: any; onClose: () => void }) {
  const [ai, setAi] = useState<any>(null);
  const [aiBusy, setAiBusy] = useState("");
  const [aiDecision, setAiDecision] = useState<string>("");
  const [detail, setDetail] = useState<any>(null);
  const [editVal, setEditVal] = useState("");
  const [editing, setEditing] = useState(false);
  const toast = useToast();

  const loadDetail = () => api.get(`/loans/${exc.loan_id}`).then(setDetail).catch(() => {});
  useEffect(() => { loadDetail(); }, [exc.loan_id]);

  const openCount = detail?.exceptions.filter((e: any) => e.status === "open").length ?? 0;

  const runAi = async (kind: string) => {
    setAiBusy(kind); setAiDecision("");
    try {
      const r = await api.post(`/exceptions/${exc.id}/ai`, { kind });
      setAi(r);
      if (r.suggested_value) setEditVal(r.suggested_value);
    } catch (e: any) { toast(e.message, "err"); }
    finally { setAiBusy(""); }
  };
  const decide = async (decision: string) => {
    if (ai?.id) await api.post(`/ai/${ai.id}/decision`, { decision });
    setAiDecision(decision);
    toast(<>AI suggestion <b>{decision}</b> · logged to audit.</>);
  };
  const resolve = async (action: string) => {
    try {
      const body: any = { action };
      if (action === "edit") { body.field = exc.field; body.new_value = editVal || exc.observed_value; }
      await api.post(`/exceptions/${exc.id}/resolve`, body);
      toast(<>Exception <b>{action === "edit" ? "corrected" : action + "ed"}</b> on {exc.loan_id}.</>);
      setEditing(false);
      loadDetail();                        // refresh the open-exception count / verify gate
    } catch (e: any) { toast(e.message, "err"); }
  };
  const verify = async () => {
    try {
      const r = await api.post(`/loans/${exc.loan_id}/verify`);
      toast(<>Loan {exc.loan_id} verified · hash <code>{r.record_hash.slice(0, 12)}…</code></>);
    } catch (e: any) { toast(e.message, "err"); }
  };

  const conf = typeof ai?.confidence === "number" ? Math.round(ai.confidence * 100) : null;

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="drawer">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2 style={{ margin: "0 0 3px" }}>Exception review</h2>
            <div className="doc-id">{exc.loan_id}</div>
          </div>
          <button className="ghost sm" onClick={onClose}>Close</button>
        </div>
        <p className="muted" style={{ margin: "10px 0 0" }}>{exc.rule_id} · {exc.message}</p>

        <div className="ai" style={{ borderLeftColor: "var(--" + exc.severity + ")" }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b className="mono">{exc.field}</b>
            <span className={"badge " + exc.severity}>{exc.severity}</span>
          </div>
          <div style={{ marginTop: 6 }}>
            observed <b>{exc.observed_value}</b> · expected <b>{exc.expected}</b>
            {exc.sibling_value ? <> · servicer <b>{exc.sibling_value}</b></> : null}
          </div>
        </div>

        <h2 style={{ marginTop: 22 }}>AI assistant</h2>
        <div className="row">
          {["explain", "suggest", "compare"].map((k) => (
            <button key={k} className="sm ghost" disabled={!!aiBusy} onClick={() => runAi(k)}>
              {aiBusy === k ? "…" : k[0].toUpperCase() + k.slice(1)}
            </button>
          ))}
        </div>
        {ai && (
          <div className="ai">
            <div className="meta">{ai.provider} · {ai.model}{conf != null ? ` · confidence ${conf}%` : ""}</div>
            {conf != null && <div className="meter"><span style={{ width: conf + "%" }} /></div>}
            <div style={{ marginTop: 8 }}>{ai.response}</div>
            {ai.suggested_value && <div style={{ marginTop: 8 }}>→ suggested: <b className="mono">{ai.suggested_value}</b></div>}
            <div className="row" style={{ marginTop: 10 }}>
              <button className="sm ghost" disabled={aiDecision === "accepted"} onClick={() => decide("accepted")}>
                {aiDecision === "accepted" ? "✓ Accepted" : "Accept"}
              </button>
              <button className="sm ghost" disabled={aiDecision === "rejected"} onClick={() => decide("rejected")}>
                {aiDecision === "rejected" ? "✕ Rejected" : "Reject"}
              </button>
            </div>
          </div>
        )}

        <h2 style={{ marginTop: 22 }}>Decision</h2>
        {editing ? (
          <div className="ai">
            <label>New value for {exc.field}</label>
            <input value={editVal} onChange={(e) => setEditVal(e.target.value)} style={{ width: "100%" }} autoFocus />
            <div className="row" style={{ marginTop: 10 }}>
              <button className="sm" onClick={() => resolve("edit")}>Save correction</button>
              <button className="sm ghost" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <div className="row">
            <button className="sm" onClick={() => setEditing(true)}>Apply edit</button>
            <button className="sm ghost" onClick={() => resolve("approve")}>Approve</button>
            <button className="sm ghost danger" onClick={() => resolve("reject")}>Reject</button>
            <button className="sm ghost" onClick={() => resolve("request_correction")}>Request fix</button>
          </div>
        )}
        <div style={{ marginTop: 14 }}>
          <button onClick={verify} disabled={openCount > 0}>✓ Verify loan</button>
          {openCount > 0 && (
            <div className="faint mono" style={{ fontSize: 11, marginTop: 6 }}>
              Resolve {openCount} open exception{openCount > 1 ? "s" : ""} on this loan before verifying.
            </div>
          )}
        </div>

        {detail && (
          <>
            <h2 style={{ marginTop: 22 }}>All exceptions on this loan ({detail.exceptions.length})</h2>
            <div className="grid" style={{ gap: 6 }}>
              {detail.exceptions.map((e: any) => (
                <div key={e.id} className="row" style={{ justifyContent: "space-between", fontSize: 12 }}>
                  <span className="mono muted">{e.rule_id} · {e.field}</span>
                  <span className={"pill " + e.status}>{e.status}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}
