import { useState } from "react";
import { api, auth } from "./api";
import Operator from "./pages/Operator";
import Reviewer from "./pages/Reviewer";
import Consumer from "./pages/Consumer";

function Login({ onLogin }: { onLogin: () => void }) {
  const [u, setU] = useState("reviewer");
  const [p, setP] = useState("reviewer123");
  const [err, setErr] = useState("");
  const go = async () => {
    try {
      const r = await api.login(u, p);
      auth.set(r.access_token, r.role);
      onLogin();
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="login card">
      <h1 style={{ marginTop: 0 }}>Loan Verification Copilot</h1>
      <p className="muted">Sign in — try <kbd>operator</kbd>, <kbd>reviewer</kbd>, or <kbd>consumer</kbd> (password = name + <kbd>123</kbd>).</p>
      <label>Username</label>
      <input value={u} onChange={(e) => setU(e.target.value)} style={{ width: "100%" }} />
      <label>Password</label>
      <input type="password" value={p} onChange={(e) => setP(e.target.value)} style={{ width: "100%" }} />
      {err && <p className="err">{err}</p>}
      <button style={{ marginTop: 14, width: "100%" }} onClick={go}>Sign in</button>
    </div>
  );
}

export default function App() {
  const [, force] = useState(0);
  const rerender = () => force((n) => n + 1);
  if (!auth.token) return <Login onLogin={rerender} />;

  const role = auth.role;
  return (
    <div>
      <div className="top">
        <h1>🏦 Loan Verification Copilot</h1>
        <div className="row">
          <span className="role">{role}</span>
          <button className="ghost sm" onClick={() => { auth.clear(); rerender(); }}>Logout</button>
        </div>
      </div>
      <div className="wrap">
        {role === "data_operator" && <Operator />}
        {role === "reviewer" && <Reviewer />}
        {role === "data_consumer" && <Consumer />}
      </div>
    </div>
  );
}
