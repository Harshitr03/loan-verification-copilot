import { useState } from "react";
import { auth } from "./api";
import Login from "./components/Login";
import Shell from "./components/Shell";
import { ToastHost } from "./ui";

export default function App() {
  const [, force] = useState(0);
  const rerender = () => force((n) => n + 1);

  if (!auth.token) return <Login onLogin={rerender} />;
  return (
    <ToastHost>
      <Shell onChange={rerender} />
    </ToastHost>
  );
}
