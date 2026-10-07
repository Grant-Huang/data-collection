// PRD 16.2 role gating + IMPLEMENTATION_PLAN.md assumption 1's "simplest current-identity
// selector": no real login, just a role switch remembered per browser. Expert role hides the
// Dashboard/Experiment Center/Admin nav entries entirely (per PRD 16.2's permission table).
import { useCallback, useState } from "react";
import type { Role } from "../api/types";

const STORAGE_KEY = "current-role";

// A first-time visitor is most likely the expert who was sent the link (B9): they land on the
// collection page without having to find the role switch first. Researchers/admins switch once
// and the choice is remembered.
const DEFAULT_ROLE: Role = "expert";

function readStored(): Role {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "expert" || raw === "researcher" || raw === "admin" ? raw : DEFAULT_ROLE;
  } catch {
    return DEFAULT_ROLE;
  }
}

export function useRole() {
  const [role, setRoleState] = useState<Role>(readStored);

  const setRole = useCallback((next: Role) => {
    setRoleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  return { role, setRole };
}
