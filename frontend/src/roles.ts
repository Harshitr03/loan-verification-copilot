// Shared role + lifecycle config, used by the login screen, header switcher, and pipeline.

export interface RoleDef {
  user: string;        // demo username (password = user + "123")
  role: string;        // backend role claim
  name: string;        // display label
  desc: string;        // short tagline
  steps: string[];     // pipeline steps this role owns
  intro: string;       // one-line "what you do here"
}

export const ROLES: RoleDef[] = [
  {
    user: "operator", role: "data_operator", name: "Operator", desc: "ingest + validate",
    steps: ["ingest", "validate"],
    intro: "Upload loan tapes — each row is normalized and checked against 15 validation rules.",
  },
  {
    user: "reviewer", role: "reviewer", name: "Reviewer", desc: "triage + verify",
    steps: ["triage", "verify"],
    intro: "Work the exception queue with AI assistance, then verify loans once their exceptions are cleared.",
  },
  {
    user: "consumer", role: "data_consumer", name: "Consumer", desc: "read + audit",
    steps: ["consume"],
    intro: "Browse verified records and inspect their tamper-evident, hash-chained audit trails.",
  },
];

export interface PipeStep { id: string; label: string; by: string; }

export const PIPELINE: PipeStep[] = [
  { id: "ingest", label: "Ingest", by: "Operator" },
  { id: "validate", label: "Validate", by: "Operator" },
  { id: "triage", label: "Triage", by: "Reviewer" },
  { id: "verify", label: "Verify", by: "Reviewer" },
  { id: "consume", label: "Consume", by: "Consumer" },
];

export const roleFor = (role: string | null): RoleDef =>
  ROLES.find((r) => r.role === role) ?? ROLES[1];
