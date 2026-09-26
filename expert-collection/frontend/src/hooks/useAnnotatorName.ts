// Remembers the annotator name per browser so it isn't retyped for every record (it used to be
// cleared each time the panel opened). Same localStorage-with-fallback pattern as useRole:
// storage can be unavailable (private mode, blocked site data), in which case the name simply
// lives for the page session.
import { useCallback, useState } from "react";

const STORAGE_KEY = "annotator-name";

function readStored(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function useAnnotatorName() {
  const [name, setNameState] = useState<string>(readStored);

  const setName = useCallback((next: string) => {
    setNameState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore -- see header comment
    }
  }, []);

  return { annotatorName: name, setAnnotatorName: setName };
}
