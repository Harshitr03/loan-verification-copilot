import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, auth } from "../api";

function jsonRes(body: any, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeEach(() => { auth.clear(); vi.restoreAllMocks(); });

describe("api client", () => {
  it("attaches the bearer token", async () => {
    auth.set("tok", "reviewer");
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonRes({ ok: true }));
    await api.get("/summary");
    const opts: any = spy.mock.calls[0][1];
    expect(opts.headers.Authorization).toBe("Bearer tok");
  });

  it("throws on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 401 }));
    await expect(api.get("/loans")).rejects.toThrow();
  });

  it("login posts form-encoded and returns the role", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonRes({ access_token: "t", role: "reviewer" }));
    const r = await api.login("u", "p");
    expect(r.role).toBe("reviewer");
    expect((spy.mock.calls[0][1] as any).body).toBeInstanceOf(URLSearchParams);
  });
});
