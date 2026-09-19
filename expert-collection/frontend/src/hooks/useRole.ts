// PRD 16.2 role gating + IMPLEMENTATION_PLAN.md assumption 1's "simplest current-identity
// selector": no real login, just a role switch remembered per browser. Expert role hides the
// Dashboard/Experiment Center/Admin nav entries entirely (per PRD 16.2's permission table).
import { useCallback, useState } from "react";
import type { Role } from "../api/types";

const STORAGE_KEY = "current-role";

function readStored(): Role {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === "expert" || raw === "researcher" || raw === "admin" ? raw : "researcher";
  } catch {
    return "researcher";
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
