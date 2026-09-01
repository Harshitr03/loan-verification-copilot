import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "../App";
import { auth } from "../api";

describe("App", () => {
  beforeEach(() => auth.clear());
  it("shows the login screen when logged out", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: /Sign in/i })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Loan Verification Copilot/i })).toBeTruthy();
  });
});
