import { useEffect, useState } from "react";
import { api } from "../api";

export default function Operator() {
  const [src, setSrc] = useState("ORIG_SYS");
  const [tape, setTape] = useState<File | null>(null);
  const [srv, setSrv] = useState<File | null>(null);
  const [man, setMan] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [history, setHistory] = useState<any[]>([]);

  const loadHistory = () => api.get("/datasets").then((r) => setHistory(r.items)).catch(() => {});
  useEffect(() => { loadHistory(); }, []);

  const upload = async () => {
    if (!tape) { setErr("loan_tape file is required"); return; }
    setBusy(true); setErr(""); setResult(null);
    try {
      const fd = new FormData();
      fd.append("loan_tape", tape);
      fd.append("source_system", src);
      if (srv) fd.append("servicer_update", srv);
      if (man) fd.append("document_manifest", man);
      const up = await api.upload(fd);
      const val = await api.post(`/datasets/${up.dataset_id}/validate`);
      setResult({ ...up, ...val });
      loadHistory();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="card">
        <h2>Upload &amp; validate a dataset</h2>
        <div className="grid cols-4" style={{ alignItems: "end" }}>
          <div>
            <label>Source system</label>
            <input value={src} onChange={(e) => setSrc(e.target.value)} style={{ width: "100%" }} />
          </div>
          <div><label>loan_tape.csv *</label><input type="file" accept=".csv" onChange={(e) => setTape(e.target.files?.[0] || null)} /></div>
          <div><label>servicer_update.csv</label><input type="file" accept=".csv" onChange={(e) => setSrv(e.target.files?.[0] || null)} /></div>
          <div><label>document_manifest.csv</label><input type="file" accept=".csv" onChange={(e) => setMan(e.target.files?.[0] || null)} /></div>
        </div>
        <div style={{ marginTop: 14 }}>
          <button disabled={busy} onClick={upload}>{busy ? "Working…" : "Upload + Validate"}</button>
          {err && <span className="err" style={{ marginLeft: 12 }}>{err}</span>}
        </div>
      </div>

      {result && (
        <div className="grid cols-4">
          <div className="tile"><div className="n">{result.row_count}</div><div className="l">Rows</div></div>
          <div className="tile"><div className="n ok">{result.imported_count}</div><div className="l">Imported</div></div>
          <div className="tile"><div className="n" style={{ color: "var(--warn)" }}>{result.failed_count}</div><div className="l">Failed</div></div>
          <div className="tile"><div className="n">{result.exceptions}</div><div className="l">Exceptions · quality {Math.round((result.quality_score ?? 0) * 100)}%</div></div>
        </div>
      )}

      <div className="card">
        <h2>Import history</h2>
        <table>
          <thead><tr><th>File</th><th>Source</th><th>Rows</th><th>Imported</th><th>Failed</th><th>Quality</th><th>Status</th></tr></thead>
          <tbody>
            {history.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td><td>{d.source_system}</td><td>{d.row_count}</td>
                <td>{d.imported_count}</td><td>{d.failed_count}</td>
                <td>{d.quality_score != null ? Math.round(d.quality_score * 100) + "%" : "—"}</td>
                <td>{d.status}</td>
              </tr>
            ))}
            {history.length === 0 && <tr><td colSpan={7} className="muted">No datasets yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
