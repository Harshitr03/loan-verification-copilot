import { useState } from "react";
import { api, auth } from "../api";
import { ROLES, RoleDef } from "../roles";
import { useToast } from "../ui";

// Masthead: brand + a "View as" role switcher that re-authenticates behind the
// scenes (real JWT per role) so all three dashboards are one click away.
export default function Header({ onChange }: { onChange: () => void }) {
  const role = auth.role!;
  const [switching, setSwitching] = useState("");
  const toast = useToast();

  const switchTo = async (r: RoleDef) => {
    if (r.role === role) return;
    setSwitching(r.user);
    try {
      const res = await api.login(r.user, r.user + "123");
      auth.set(res.access_token, res.role);
      onChange();
    } catch (e: any) { toast("Couldn't switch role — " + e.message, "err"); }
    finally { setSwitching(""); }
  };

  return (
    <div className="top">
      <div className="brand">
        <h1><span className="seal" aria-hidden>LV</span> Loan Verification Copilot</h1>
        <span className="tag">Ledger</span>
      </div>
      <div className="viewas">
        <span className="viewas-label">View as</span>
        <div className="role-switch">
          {ROLES.map((r) => (
            <button key={r.user} className={"role-tab" + (r.role === role ? " active" : "")}
              onClick={() => switchTo(r)} disabled={!!switching} title={`${r.name}: ${r.desc}`}>
              {switching === r.user ? "…" : r.name}
            </button>
          ))}
        </div>
      </div>
      <button className="ghost sm" onClick={() => { auth.clear(); onChange(); }}>Sign out</button>
    </div>
  );
}
