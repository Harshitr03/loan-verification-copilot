# Demo Video Script — Loan Data Verification Copilot (~5 min)

**Live app:** https://loan-verification-copilot.web.app · **API/Swagger:** https://lvc-api-819197160245.asia-south1.run.app/docs
**Credentials:** operator/operator123 · reviewer/reviewer123 · consumer/consumer123

Format below: **[time] — what you SAY (narration) — [DO: on-screen action]**. Aim to keep the mouse deliberate; pause on the highlighted moments.

---

## 0:00–0:30 · Hook + what it is
> "Loan data almost never arrives clean — it comes from CSVs, servicing systems, spreadsheets. Before anyone can trust it, someone has to catch the errors, decide what to do, and produce a verified, auditable record. This is the Loan Data Verification Copilot — an AI-assisted console that does exactly that."

**[DO:** Land on the login screen. Point at the role picker.]** "Three roles — Operator, Reviewer, Consumer — and the whole pipeline runs end to end."

---

## 0:30–1:40 · Operator — ingest + validate (Modules A + B)
**[DO:** Sign in as Operator. Point at the pipeline strip — *Ingest → Validate* lit up.]**
> "The Operator uploads a loan tape. Every row is stored raw for lineage, normalized into a canonical schema, then checked against 15 validation rules."

**[DO:** Upload the three sample CSVs → click **Upload + validate**. Point at the result tiles.]**
> "3,000 rows in — imported, a handful of un-normalizable rows separated out as failed imports, and around 650 exceptions raised. Notice the data-quality score — it's severity-weighted, not just a count."

**[DO:** Point at Import history row.]** "Every upload is tracked with full lineage."

---

## 1:40–3:15 · Reviewer — triage with AI + verify (Modules C, D, E)
**[DO:** Click **Reviewer** in the "View as" switcher — instant, no re-login. Pipeline shifts to *Triage → Verify*.]**
> "One click to the Reviewer. Here's the exception queue — filterable by severity and status."

**[DO:** Open one exception (e.g. a negative principal or a servicer conflict). The drawer opens.]**
> "Open a loan and you get a clear three-step flow. **Step one — Understand.** I ask the AI to explain why it failed."

**[DO:** Click **Explain**. Point at the response + confidence + the 'provider · model' line.]**
> "The AI explains it in plain language — and critically, it's advisory only. It never changes data, and every suggestion is logged to the audit trail with its model and confidence. **Step two — Decide.**"

**[DO:** Click **Compare** or **Suggest**, then **Apply edit** → show the inline correction, save. Or Approve.]**
> "I can accept the AI's suggestion, edit the value myself, approve, or reject — the human is always in control."

**[DO:** Resolve the remaining exceptions on the loan, then click **Verify loan**.]**
> "**Step three — Verify.** Notice I couldn't verify until every exception was resolved — a record can't be 'trusted' while it still has open defects. Now it's sealed into a hash-chained verified record."

---

## 3:15–4:20 · Consumer — verified data + audit trail (Modules F, G, H)
**[DO:** Click **Consumer**. Pipeline shifts to *Consume*.]**
> "The Consumer sees only trusted output — verified records, each with its record hash."

**[DO:** Click **View trail** on the loan you just verified.]**
> "And here's the payoff: a complete, tamper-evident audit trail. Every event — uploaded, validated, AI-recommended, edited, verified — is hash-linked to the one before it. The seal says **chain intact**; change any record and the chain breaks."

**[DO:** Click **Export CSV**, then open the API URL /docs in another tab, expand GET /verified-loans → Execute.]**
> "It's all exposed through a read API — here's the live Swagger, returning the same verified records as JSON."

---

## 4:20–4:50 · Traceability + agentic coding
> "Everything traces back: a verified value → its loan → the exact raw row it came from, with two independent hash chains proving nothing was tampered with."

**[DO:** Briefly show the AI Development Log (docs/ai-development-log.md).]**
> "And this was built with agentic coding throughout — the AI Development Log records the prompts, what we accepted, and the cases where the AI was wrong and we caught it in review."

---

## 4:50–5:00 · Close
> "Messy loan tape in, verified and auditable data out — with AI assisting a human at every step, and a full paper trail. Deployed and running on Firebase, Cloud Run, and MongoDB Atlas. Thanks for watching."

---

## Pre-record checklist
- [ ] **Redeploy the frontend** so the new UX (role switcher, pipeline, drawer steps) is live: `cd frontend && VITE_API_BASE="https://lvc-api-819197160245.asia-south1.run.app" npm run build && cd .. && firebase deploy`.
- [ ] **Warm the backend** first (Cloud Run cold start): open the app once ~1 min before recording, or `curl .../health`.
- [ ] Have `sample_data/*.csv` ready on the desktop for the upload step.
- [ ] Optional: reset to a clean demo state beforehand (drop the `lvc` DB in Atlas, re-run `python -m backend.app.demo_seed`) so counts look tidy — or just upload live.
- [ ] Keep it under 5:00 (the hard limit).
