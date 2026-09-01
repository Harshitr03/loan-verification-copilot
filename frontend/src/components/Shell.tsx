import { auth } from "../api";
import { roleFor } from "../roles";
import Header from "./Header";
import Pipeline from "./Pipeline";
import Operator from "../pages/Operator";
import Reviewer from "../pages/Reviewer";
import Consumer from "../pages/Consumer";

// The authenticated app frame: header + lifecycle pipeline + the active role's page.
export default function Shell({ onChange }: { onChange: () => void }) {
  const role = auth.role!;
  const current = roleFor(role);

  return (
    <>
      <Header onChange={onChange} />
      <Pipeline activeSteps={current.steps} />
      <div className="wrap">
        <p className="role-intro">{current.intro}</p>
        {role === "data_operator" && <Operator />}
        {role === "reviewer" && <Reviewer />}
        {role === "data_consumer" && <Consumer />}
      </div>
    </>
  );
}
