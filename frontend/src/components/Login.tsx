import { useState } from "react";
import { api, auth } from "../api";
import { ROLES } from "../roles";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [u, setU] = useState("reviewer");
  const [p, setP] = useState("reviewer123");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const pick = (user: string) => { setU(user); setP(user + "123"); setErr(""); };

  const go = async () => {
    setBusy(true); setErr("");
    try {
      const r = await api.login(u, p);
      auth.set(r.access_token, r.role);
      onLogin();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="login-shell">
      <div className="login">
        <div className="mark" aria-hidden>LV</div>
        <h1>Loan Verification Copilot</h1>
        <p className="sub">Sign in to the verification desk. Pick a role to autofill demo credentials — you can switch roles anytime once you're in.</p>

        <label>Role</label>
        <div className="segmented">
          {ROLES.map((r) => (
            <button key={r.user} type="button" className="seg" aria-pressed={u === r.user}
              onClick={() => pick(r.user)}>
              <span className="rname">{r.name}</span>
              <span className="rdesc">{r.desc}</span>
            </button>
          ))}
        </div>

        <label htmlFor="u">Username</label>
        <input id="u" value={u} onChange={(e) => setU(e.target.value)} style={{ width: "100%" }}
          onKeyDown={(e) => e.key === "Enter" && go()} />
        <label htmlFor="p" style={{ marginTop: 12 }}>Password</label>
        <input id="p" type="password" value={p} onChange={(e) => setP(e.target.value)} style={{ width: "100%" }}
          onKeyDown={(e) => e.key === "Enter" && go()} />

        {err && <p className="err" style={{ marginTop: 12 }}>{err}</p>}
        <button style={{ marginTop: 18, width: "100%" }} disabled={busy} onClick={go}>
          {busy ? <><span className="spin" /> Signing in…</> : "Sign in"}
        </button>
      </div>
    </div>
  );
}
