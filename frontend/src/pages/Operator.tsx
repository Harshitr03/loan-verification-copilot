import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SkeletonRows, Spinner, useToast } from "../ui";

function FileField({ label, required, file, onChange }:
  { label: string; required?: boolean; file: File | null; onChange: (f: File | null) => void }) {
  return (
    <div className={"filefield" + (required ? " req" : "") + (file ? " filled" : "")}>
      <label>{label}</label>
      <input type="file" accept=".csv" onChange={(e) => onChange(e.target.files?.[0] || null)} />
      {file && <div className="fname">✓ {file.name}</div>}
    </div>
  );
}

export default function Operator() {
  const [src, setSrc] = useState("ORIG_SYS");
  const [tape, setTape] = useState<File | null>(null);
  const [srv, setSrv] = useState<File | null>(null);
  const [man, setMan] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [history, setHistory] = useState<any[] | null>(null);
  const toast = useToast();

  const loadHistory = () => api.get("/datasets").then((r) => setHistory(r.items)).catch(() => setHistory([]));
  useEffect(() => { loadHistory(); }, []);

  const upload = async () => {
    if (!tape) { setErr("Add a loan_tape.csv to continue — it's the required file."); return; }
    setBusy(true); setErr(""); setResult(null);
    try {
      const fd = new FormData();
      fd.append("loan_tape", tape);
      fd.append("source_system", src);
      if (srv) fd.append("servicer_update", srv);
      if (man) fd.append("document_manifest", man);
      const up = await api.upload(fd);
      const val = await api.post(`/datasets/${up.dataset_id}/validate`);
      const r = { ...up, ...val };
      setResult(r);
      toast(<>Imported <b>{r.imported_count}</b> loans · <b>{r.exceptions}</b> exceptions raised.</>);
      loadHistory();
    } catch (e: any) { setErr(e.message); toast("Upload failed — " + e.message, "err"); }
    finally { setBusy(false); }
  };

  const q = (n?: number) => (n != null ? Math.round(n * 100) + "%" : "—");

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div>
        <div className="eyebrow"><span className="idx">01</span> Ingest</div>
        <div className="card">
          <h2>Upload &amp; validate a dataset</h2>
          <div style={{ maxWidth: 260, marginBottom: 14 }}>
            <label>Source system</label>
            <input value={src} onChange={(e) => setSrc(e.target.value)} style={{ width: "100%" }} />
          </div>
          <div className="grid cols-3">
            <FileField label="loan_tape.csv" required file={tape} onChange={setTape} />
            <FileField label="servicer_update.csv" file={srv} onChange={setSrv} />
            <FileField label="document_manifest.csv" file={man} onChange={setMan} />
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <button disabled={busy} onClick={upload}>
              {busy ? <><Spinner /> Validating…</> : "Upload + validate"}
            </button>
            {err && <span className="err">{err}</span>}
          </div>
        </div>
      </div>

      {result && (
        <div>
          <div className="eyebrow"><span className="idx">02</span> Result</div>
          <div className="grid cols-4">
            <div className="tile accent"><span className="n">{result.row_count}</span><div className="l">Rows read</div></div>
            <div className="tile good"><span className="n ok">{result.imported_count}</span><div className="l">Imported</div></div>
            <div className="tile warn"><span className="n" style={{ color: "var(--warn)" }}>{result.failed_count}</span><div className="l">Failed rows</div></div>
            <div className="tile"><span className="n">{result.exceptions}</span><div className="l">Exceptions · quality {q(result.quality_score)}</div></div>
          </div>
        </div>
      )}

      <div>
        <div className="eyebrow"><span className="idx">≡</span> History</div>
        <div className="card">
          <h2>Import history</h2>
          <table>
            <thead><tr><th>File</th><th>Source</th><th>Rows</th><th>Imported</th><th>Failed</th><th>Quality</th><th>Status</th></tr></thead>
            <tbody>
              {history === null && <SkeletonRows cols={7} />}
              {history?.map((d) => (
                <tr key={d.id}>
                  <td className="cell-strong">{d.filename}</td>
                  <td className="mono">{d.source_system}</td>
                  <td className="num">{d.row_count}</td>
                  <td className="num ok">{d.imported_count}</td>
                  <td className="num">{d.failed_count}</td>
                  <td className="num">{q(d.quality_score)}</td>
                  <td><span className={"pill " + d.status}>{d.status}</span></td>
                </tr>
              ))}
              {history?.length === 0 && (
                <tr><td colSpan={7}><Empty icon="↑" title="No datasets yet"
                  hint="Upload a loan tape above to run it through the 15 validation rules." /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
