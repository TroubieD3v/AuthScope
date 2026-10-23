import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Severity, Verdict } from "./api";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

export const VERDICT_META: Record<Verdict, { label: string; tone: "bad" | "warn" | "ok" | "mute" | "info" }> = {
  violation: { label: "Policy violation", tone: "bad" },
  needs_review: { label: "Needs review", tone: "warn" },
  pass: { label: "Passed", tone: "ok" },
  inconclusive: { label: "Inconclusive", tone: "info" },
  skipped: { label: "Skipped", tone: "mute" },
  error: { label: "Error", tone: "bad" },
};

export const SEVERITY_TONE: Record<Severity, "bad" | "warn" | "ok" | "mute" | "info"> = {
  critical: "bad", high: "bad", medium: "warn", low: "info", info: "mute",
};

export const MODULE_LABEL: Record<string, string> = {
  bola: "BOLA / IDOR", bfla: "BFLA", bopla: "BOPLA", unauth: "Unauthenticated", tenant: "Cross-Tenant", custom: "Custom",
};

export const fmtTime = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "-");
export const copy = (text: string) => navigator.clipboard?.writeText(text);
