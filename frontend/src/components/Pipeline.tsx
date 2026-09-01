import { PIPELINE } from "../roles";

// The loan lifecycle strip: Ingest → Validate → Triage → Verify → Consume,
// highlighting the steps owned by the current role.
export default function Pipeline({ activeSteps }: { activeSteps: string[] }) {
  return (
    <div className="pipeline" aria-label="Loan lifecycle">
      {PIPELINE.map((s, i) => (
        <div className="pipeline-item" key={s.id}>
          <div className={"pstep" + (activeSteps.includes(s.id) ? " active" : "")} title={`${s.label} — ${s.by}`}>
            <span className="pnum">{i + 1}</span>
            <span className="plabel">{s.label}</span>
          </div>
          {i < PIPELINE.length - 1 && <span className="parrow" aria-hidden>→</span>}
        </div>
      ))}
    </div>
  );
}
