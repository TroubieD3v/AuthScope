import { ChevronDown, ChevronRight, Copy, Download, GitCompare } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { useApp } from "@/ctx";
import { api, type CheckResult, type Exchange, type Run } from "@/lib/api";
import { copy, fmtTime, MODULE_LABEL, SEVERITY_TONE } from "@/lib/utils";
import { PageHeader, VerdictBadge } from "./common";

type Tab = "findings" | "passed" | "other";
const SEV_ORDER = ["critical", "high", "medium", "low", "info"];

export function Findings() {
  const { project, focusRun, notify } = useApp();
  const [runs, setRuns] = useState<Run[]>([]);
  const [rid, setRid] = useState<string | null>(focusRun);
  const [all, setAll] = useState<CheckResult[]>([]);
  const [detail, setDetail] = useState<Record<string, CheckResult>>({});
  const [tab, setTab] = useState<Tab>("findings");
  const [module, setModule] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [diff, setDiff] = useState<{ new: CheckResult[]; fixed: CheckResult[]; unchanged: CheckResult[] } | null>(null);

  useEffect(() => {
    api.runs(project.id).then((rs) => {
      const done = rs.filter((r) => r.status !== "queued" && r.status !== "running");
      setRuns(done);
      setRid((cur) => cur ?? done[0]?.id ?? null);
    });
  }, [project.id]);

  useEffect(() => {
    setDiff(null); setOpen(null);
    if (!rid) { setAll([]); return; }
    Promise.all([api.results(rid, "all"), api.results(rid, "findings")]).then(([light, full]) => {
      setAll(light);
      setDetail(Object.fromEntries(full.map((f) => [f.id, f])));
    });
  }, [rid]);

  const view = useMemo(() => {
    const byTab = all.filter((r) =>
      tab === "findings" ? r.verdict === "violation" || r.verdict === "needs_review"
        : tab === "passed" ? r.verdict === "pass" : ["inconclusive", "skipped", "error"].includes(r.verdict));
    return byTab.filter((r) => !module || r.module === module).sort((a, b) =>
      (a.verdict === b.verdict ? 0 : a.verdict === "violation" ? -1 : b.verdict === "violation" ? 1 : 0) ||
      SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity));
  }, [all, tab, module]);

  const counts = {
    findings: all.filter((r) => r.verdict === "violation" || r.verdict === "needs_review").length,
    passed: all.filter((r) => r.verdict === "pass").length,
    other: all.filter((r) => ["inconclusive", "skipped", "error"].includes(r.verdict)).length,
  };
  const idx = runs.findIndex((r) => r.id === rid);
  const previous = idx >= 0 ? runs[idx + 1] : undefined;

  const expand = async (r: CheckResult) => {
    setOpen(open === r.id ? null : r.id);
    if (!detail[r.id] && rid) {
      try { setDetail({ ...detail, [r.id]: await api.result(rid, r.id) }); } catch (e) { notify(String(e), "bad"); }
    }
  };

  return (
    <div className="space-y-10">
      <PageHeader kicker={counts.findings ? `${counts.findings} to fix or review` : "Evidence"} kickerTone={counts.findings ? "bad" : "accent"} title="Findings & Reports" hint="Both requests side by side, the response differences, the expected policy and a curl to reproduce it. Tokens are masked."
        actions={rid && (
          <>
            {(["html", "md", "json", "pytest"] as const).map((f) => (
              <a key={f} href={api.reportUrl(rid, f)}>
                <Button size="sm" variant="secondary"><Download className="size-3.5" /> {f === "md" ? "Markdown" : f === "pytest" ? "pytest" : f.toUpperCase()}</Button>
              </a>
            ))}
          </>
        )} />

      <div className="flex flex-wrap items-center gap-3">
        <Select className="w-72" value={rid ?? ""} onChange={(e) => setRid(e.target.value)}>
          {runs.length === 0 && <option value="">No finished runs</option>}
          {runs.map((r) => <option key={r.id} value={r.id}>{r.id} - {fmtTime(r.started_at)} - {r.stats.by_verdict.violation ?? 0} violations</option>)}
        </Select>
        <Select className="w-44" value={module} onChange={(e) => setModule(e.target.value)}>
          <option value="">All modules</option>
          {[...new Set(all.map((r) => r.module))].map((m) => <option key={m} value={m}>{MODULE_LABEL[m] ?? m}</option>)}
        </Select>
        {rid && previous && (
          <Button size="sm" variant="secondary" onClick={() => api.diff(rid, previous.id).then(setDiff)}>
            <GitCompare className="size-3.5" /> Compare with {previous.id}
          </Button>
        )}
        <div className="ml-auto flex gap-1 rounded-[3px] bg-panel2 p-1">
          {(["findings", "passed", "other"] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`cursor-pointer rounded-[3px] px-3 py-1.5 text-xs font-semibold ${tab === t ? "bg-primary text-on-primary" : "text-mute hover:text-ink"}`}>
              {t === "findings" ? "Findings" : t === "passed" ? "Passed" : "Inconclusive / skipped"} <span className="font-mono">{counts[t]}</span>
            </button>
          ))}
        </div>
      </div>

      {diff && (
        <Card>
          <CardHeader title="Regression: compared with previous run" actions={<Button size="sm" variant="ghost" onClick={() => setDiff(null)}>Close</Button>} />
          <div className="grid grid-cols-3 divide-x divide-line/60 text-sm">
            {([["New", diff.new, "text-bad"], ["Fixed", diff.fixed, "text-ok"], ["Unchanged", diff.unchanged, "text-mute"]] as const).map(([t, list, cls]) => (
              <div key={t} className="p-4">
                <div className={`mb-2 font-mono text-2xl ${cls}`}>{list.length}</div>
                <div className="mb-2 text-xs uppercase tracking-wider text-mute">{t}</div>
                <ul className="max-h-40 space-y-1 overflow-y-auto text-xs">{list.map((r) => <li key={r.id} className="truncate" title={r.name}>{r.name}</li>)}</ul>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="divide-y divide-line/60">
        {rid && view.length === 0 && (
          <p className="px-5 py-8 text-center text-sm text-mute">{tab === "findings" ? "No violations - everything matches the policy." : "Nothing here."}</p>
        )}
        {!rid && <p className="px-5 py-8 text-center text-sm text-mute">Run a test first.</p>}
        {view.map((r) => (
          <div key={r.id}>
            <button onClick={() => expand(r)} className="flex w-full cursor-pointer items-start gap-3 px-5 py-3 text-left hover:bg-panel2/50">
              {open === r.id ? <ChevronDown className="mt-0.5 size-4 shrink-0 text-mute" /> : <ChevronRight className="mt-0.5 size-4 shrink-0 text-mute" />}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <VerdictBadge v={r.verdict} />
                  {r.verdict !== "pass" && r.verdict !== "skipped" && <Badge tone={SEVERITY_TONE[r.severity]}>{r.severity}</Badge>}
                  <Badge>{MODULE_LABEL[r.module] ?? r.module}</Badge>
                  <span className="text-sm font-medium">{r.name}</span>
                </div>
                <p className="mt-1 text-xs text-mute">{r.message}</p>
              </div>
            </button>
            {open === r.id && <EvidenceView r={detail[r.id] ?? r} />}
          </div>
        ))}
      </Card>
    </div>
  );
}

function EvidenceView({ r }: { r: CheckResult }) {
  const ev = r.evidence;
  if (!ev) return <p className="bg-panel2/40 px-12 py-4 text-xs text-mute">No request evidence for this result (it was {r.verdict}).</p>;
  return (
    <div className="space-y-4 bg-panel2/40 px-12 py-4">
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div><div className="mb-1 font-semibold uppercase tracking-wider text-mute">Expected policy</div><p>{ev.expected || "-"}</p></div>
        <div><div className="mb-1 font-semibold uppercase tracking-wider text-mute">Analysis</div>
          <ul className="list-disc space-y-0.5 pl-4">{ev.diff.map((d) => <li key={d}>{d}</li>)}</ul></div>
      </div>
      <div className={`grid gap-4 ${ev.baseline ? "grid-cols-2" : "grid-cols-1"}`}>
        {ev.baseline && <Exchange title="Baseline" ex={ev.baseline} />}
        {ev.test && <Exchange title="Test" ex={ev.test} />}
      </div>
      {ev.reproduction.length > 0 && (
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-mute">Reproduce (tokens come from env variables)</span>
            <Button size="sm" variant="ghost" onClick={() => copy(ev.reproduction.join("\n\n"))}><Copy className="size-3" /> Copy</Button>
          </div>
          <pre className="overflow-x-auto rounded-2xl bg-bg ring-1 ring-line/60 p-3 text-[11px] leading-relaxed">{ev.reproduction.join("\n\n")}</pre>
        </div>
      )}
    </div>
  );
}

function Exchange({ title, ex }: { title: string; ex: Exchange }) {
  const tone = ex.status === null ? "bad" : ex.status < 300 ? "ok" : ex.status < 500 ? "warn" : "bad";
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center gap-2 text-xs">
        <span className="font-semibold uppercase tracking-wider text-mute">{title}</span>
        <Badge>{ex.identity ?? "anonymous"}</Badge>
        <Badge tone={tone}>{ex.status ?? "ERR"}</Badge>
        <span className="text-mute">{ex.elapsed_ms} ms</span>
      </div>
      <pre className="mb-1.5 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-2xl bg-bg ring-1 ring-line/60 p-2.5 text-[11px]">
        {ex.method} {ex.url}{Object.entries(ex.request_headers).map(([k, v]) => `\n${k}: ${v}`).join("")}{ex.request_body ? `\n\n${ex.request_body}` : ""}
      </pre>
      <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all rounded-2xl bg-bg ring-1 ring-line/60 p-2.5 text-[11px]">{ex.error ?? ex.response_body ?? "(empty body)"}</pre>
    </div>
  );
}
