const BASE = (import.meta as any).env.VITE_API_BASE || "/api";

let token: string | null = sessionStorage.getItem("tok");
let role: string | null = sessionStorage.getItem("role");

export const auth = {
  get token() { return token; },
  get role() { return role; },
  set(t: string, r: string) {
    token = t; role = r;
    sessionStorage.setItem("tok", t); sessionStorage.setItem("role", r);
  },
  clear() { token = null; role = null; sessionStorage.clear(); },
};

async function req(path: string, opts: RequestInit = {}) {
  const headers: any = { ...(opts.headers || {}) };
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(BASE + path, { ...opts, headers });
  if (!res.ok) throw new Error(res.status + ": " + (await res.text()));
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

export const api = {
  login: async (u: string, p: string) => {
    const res = await fetch(BASE + "/auth/login", {
      method: "POST", body: new URLSearchParams({ username: u, password: p }),
    });
    if (!res.ok) throw new Error("Invalid credentials");
    return res.json();
  },
  get: (p: string) => req(p),
  post: (p: string, b?: any) =>
    req(p, { method: "POST", headers: b ? { "Content-Type": "application/json" } : {}, body: b ? JSON.stringify(b) : undefined }),
  upload: (form: FormData) => req("/datasets", { method: "POST", body: form }),
  download: (p: string) => fetch(BASE + p, { headers: token ? { Authorization: "Bearer " + token } : {} }),
};
