import { createContext, useContext } from "react";
import type { Project } from "./lib/api";

export type Screen = "dashboard" | "explorer" | "identities" | "matrix" | "runner" | "findings";

export interface AppCtx {
  project: Project;
  reload: () => Promise<void>;
  go: (s: Screen) => void;
  notify: (msg: string, kind?: "ok" | "bad") => void;
  /** run the findings screen should show */
  focusRun: string | null;
  setFocusRun: (id: string | null) => void;
}

export const Ctx = createContext<AppCtx | null>(null);
export function useApp(): AppCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("outside provider");
  return v;
}

/** Wraps an async action: shows errors as toasts. */
export function useAction() {
  const { notify } = useApp();
  return async <T,>(fn: () => Promise<T>, okMsg?: string): Promise<T | undefined> => {
    try {
      const r = await fn();
      if (okMsg) notify(okMsg, "ok");
      return r;
    } catch (e) {
      notify(e instanceof Error ? e.message : String(e), "bad");
      return undefined;
    }
  };
}
