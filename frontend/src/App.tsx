import { Activity, FlaskConical, Grid3x3, KeyRound, LayoutDashboard, ListTree, ShieldAlert, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Ctx, type Screen } from "./ctx";
import { api, type Project, type ProjectSummary } from "./lib/api";
import { cn } from "./lib/utils";
import { Dashboard } from "./screens/Dashboard";
import { Explorer } from "./screens/Explorer";
import { Findings } from "./screens/Findings";
import { Identities } from "./screens/Identities";
import { Matrix } from "./screens/Matrix";
import { Onboarding } from "./screens/Onboarding";
import { Runner } from "./screens/Runner";

const NAV: { id: Screen; label: string; icon: typeof Activity }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "explorer", label: "API Explorer", icon: ListTree },
  { id: "identities", label: "Identity Manager", icon: KeyRound },
  { id: "matrix", label: "Permission Matrix", icon: Grid3x3 },
  { id: "runner", label: "Test Runner", icon: FlaskConical },
  { id: "findings", label: "Findings & Reports", icon: ShieldAlert },
];

export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [pid, setPid] = useState<string | null>(() => localStorage.getItem("authscope.project"));
  const [project, setProject] = useState<Project | null>(null);
  const [screen, setScreen] = useState<Screen>(() => (location.hash.slice(1) as Screen) || "dashboard");
  const [focusRun, setFocusRun] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "bad" } | null>(null);

  const notify = useCallback((msg: string, kind: "ok" | "bad" = "ok") => {
    setToast({ msg, kind });
    setTimeout(() => setToast(null), kind === "bad" ? 6000 : 2500);
  }, []);

  const loadProjects = useCallback(async () => {
    const list = await api.projects();
    setProjects(list);
    return list;
  }, []);

  const reload = useCallback(async () => {
    if (pid) setProject(await api.project(pid));
  }, [pid]);

  useEffect(() => {
    loadProjects().then((list) => {
      if (!creating && !list.some((p) => p.id === pid)) setPid(list[0]?.id ?? null);
    }).catch((e) => notify(String(e), "bad"));
  }, [loadProjects, notify, pid, creating]);

  useEffect(() => {
    if (pid) {
      localStorage.setItem("authscope.project", pid);
      api.project(pid).then(setProject).catch(() => setProject(null));
    } else setProject(null);
  }, [pid]);

  const go = (s: Screen) => { setScreen(s); location.hash = s; };

  useEffect(() => {
    const onHash = () => { const h = location.hash.slice(1) as Screen; if (NAV.some((n) => n.id === h)) setScreen(h); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (projects === null) return <div className="grid h-full place-items-center text-mute">Loading...</div>;
  if (creating || !pid || !project) {
    return (
      <Onboarding
        onCreated={async (id) => { await loadProjects(); setPid(id); setCreating(false); }}
        onCancel={pid && project ? () => setCreating(false) : undefined}
        notify={notify}
      />
    );
  }

  const View = { dashboard: Dashboard, explorer: Explorer, identities: Identities, matrix: Matrix, runner: Runner, findings: Findings }[screen];

  return (
    <Ctx.Provider value={{ project, reload, go, notify, focusRun, setFocusRun }}>
      <div className="flex h-full">
        <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-panel/70 backdrop-blur">
          <div className="px-5 pb-4 pt-5">
            <div className="flex items-center gap-2.5">
              <div className="grid size-8 place-items-center rounded-lg bg-accent/15 ring-1 ring-accent/40">
                <ShieldAlert className="size-4 text-accent" />
              </div>
              <div>
                <div className="text-[15px] font-semibold leading-4 tracking-tight">AuthScope</div>
                <div className="text-[10px] uppercase tracking-widest text-mute">API Authorization Testing</div>
              </div>
            </div>
          </div>
          <nav className="flex-1 space-y-0.5 px-3">
            {NAV.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => go(id)}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-left text-[13px] transition-colors",
                  screen === id ? "bg-accent/12 text-accent" : "text-mute hover:bg-panel2 hover:text-ink",
                )}
              >
                <Icon className="size-4" /> {label}
              </button>
            ))}
          </nav>
          <div className="space-y-2 border-t border-line p-3">
            <select
              value={pid}
              onChange={(e) => e.target.value === "__new" ? setCreating(true) : setPid(e.target.value)}
              className="h-8 w-full cursor-pointer rounded-md border border-line bg-bg/70 px-2 text-xs"
            >
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              <option value="__new">+ New project...</option>
            </select>
            <div className="truncate px-1 font-mono text-[11px] text-mute" title={project.target.base_url}>{project.target.base_url}</div>
            <button
              onClick={async () => {
                if (!confirm(`Delete project "${project.name}" with all runs?`)) return;
                await api.deleteProject(pid);
                const list = await loadProjects();
                setPid(list[0]?.id ?? null);
              }}
              className="flex cursor-pointer items-center gap-1.5 px-1 text-[11px] text-mute hover:text-bad"
            >
              <Trash2 className="size-3" /> Delete project
            </button>
          </div>
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1180px] px-8 py-7"><View /></div>
        </main>
      </div>
      {toast && (
        <div
          role="status"
          className={cn(
            "fixed bottom-5 right-5 z-50 max-w-md rounded-lg border px-4 py-3 text-sm shadow-xl",
            toast.kind === "ok" ? "border-ok/40 bg-[#0d2a22] text-ok" : "border-bad/40 bg-[#2d1215] text-bad",
          )}
        >
          {toast.msg}
        </div>
      )}
    </Ctx.Provider>
  );
}
