import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

/* ---------- toast system ---------- */
type Toast = { id: number; msg: ReactNode; kind: "ok" | "err" };
const ToastCtx = createContext<(msg: ReactNode, kind?: "ok" | "err") => void>(() => {});

export function useToast() { return useContext(ToastCtx); }

export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((msg: ReactNode, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, msg, kind }]);
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toaster" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={"toast " + (t.kind === "err" ? "err" : "")}>
            <span className="ic">{t.kind === "err" ? "⚠" : "✓"}</span>
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------- primitives ---------- */
export function Empty({ icon = "—", title, hint }: { icon?: string; title: string; hint?: string }) {
  return (
    <div className="empty">
      <div className="big">{icon}</div>
      <div className="t">{title}</div>
      {hint && <div>{hint}</div>}
    </div>
  );
}

export function Spinner() { return <span className="spin" aria-hidden />; }

export function SkeletonRows({ cols, rows = 4 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((__, c) => (
            <td key={c}><div className="skel" style={{ width: c === 0 ? "60%" : "80%" }} /></td>
          ))}
        </tr>
      ))}
    </>
  );
}

/* short-hash renderer, monospace */
export function Hash({ value, len = 16 }: { value?: string; len?: number }) {
  if (!value) return <span className="faint">—</span>;
  return <span className="hash" title={value}>{value.slice(0, len)}…</span>;
}
