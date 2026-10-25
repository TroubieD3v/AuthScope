import { FlaskConical, Grid3x3, KeyRound, LayoutDashboard, ListTree, ShieldAlert, Trash2 } from "lucide-react";
import { Logo } from "./components/logo";
import { useCallback, useEffect, useState } from "react";
import { Ctx, type Screen } from "./ctx";
import { api, type Project, type ProjectSummary } from "./lib/api";
import { ThemeToggle } from "./lib/theme";
import { cn } from "./lib/utils";
import { Dashboard } from "./screens/Dashboard";
import { Explorer } from "./screens/Explorer";
import { Findings } from "./screens/Findings";
import { Identities } from "./screens/Identities";
import { Matrix } from "./screens/Matrix";
import { Onboarding } from "./screens/Onboarding";
import { Runner } from "./screens/Runner";

const NAV: { id: Screen; label: string; short: string; icon: typeof ShieldAlert }[] = [
  { id: "dashboard", label: "Dashboard", short: "Dashboard", icon: LayoutDashboard },
  { id: "explorer", label: "API Explorer", short: "Explorer", icon: ListTree },
  { id: "identities", label: "Identity Manager", short: "Identities", icon: KeyRound },
  { id: "matrix", label: "Permission Matrix", short: "Matrix", icon: Grid3x3 },
  { id: "runner", label: "Test Runner", short: "Runner", icon: FlaskConical },
  { id: "findings", label: "Findings & Reports", short: "Findings", icon: ShieldAlert },
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

  const go = (s: Screen) => { setScreen(s); location.hash = s; window.scrollTo({ top: 0 }); };

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
  const deleteProject = async () => {
    if (!confirm(`Delete project "${project.name}" with all runs?`)) return;
    await api.deleteProject(pid);
    const list = await loadProjects();
    setPid(list[0]?.id ?? null);
  };

  return (
    <Ctx.Provider value={{ project, reload, go, notify, focusRun, setFocusRun }}>
      {/* Top app bar */}
      <header className="sticky top-0 z-40 border-b border-line/60 bg-bg/75 backdrop-blur-xl">
        <div className="mx-auto flex h-[68px] max-w-[1400px] items-center justify-between gap-4 px-5 lg:px-8">
          <Logo />
          <div className="flex items-center gap-2">
            <select
              value={pid}
              aria-label="Project"
              onChange={(e) => e.target.value === "__new" ? setCreating(true) : setPid(e.target.value)}
              className="hidden h-9 max-w-[16rem] cursor-pointer rounded-[3px] border border-line bg-panel2/70 px-3 text-xs font-medium sm:block"
            >
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              <option value="__new">+ New project...</option>
            </select>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1400px]">
        {/* Desktop rail */}
        <aside className="sticky top-[68px] hidden h-[calc(100vh-68px)] w-64 shrink-0 flex-col justify-between px-5 py-8 lg:flex">
          <nav className="space-y-1.5">
            {NAV.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => go(id)}
                className={cn(
                  "group flex w-full cursor-pointer items-center gap-3 rounded-[3px] px-2 py-1.5 text-left text-[13.5px] font-medium transition-colors",
                  screen === id ? "text-ink" : "text-mute hover:text-ink",
                )}
              >
                <span className={cn(
                  "grid size-9 place-items-center rounded-[3px] transition-colors",
                  screen === id ? "bg-primary text-on-primary" : "group-hover:bg-panel2",
                )}>
                  <Icon className="size-[18px]" />
                </span>
                {label}
              </button>
            ))}
          </nav>
          <div className="space-y-3 rounded-2xl bg-panel2 p-4">
            <div className="text-[10.5px] font-bold uppercase tracking-[0.14em] text-mute">Target</div>
            <div className="truncate font-mono text-xs" title={project.target.base_url}>{project.target.base_url}</div>
            <button onClick={deleteProject} className="flex cursor-pointer items-center gap-1.5 text-[11px] text-mute hover:text-bad">
              <Trash2 className="size-3" /> Delete project
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-5 pb-32 pt-8 lg:px-10 lg:pb-16">
          <div className="mx-auto max-w-[1080px]"><View /></div>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line/60 bg-bg/85 backdrop-blur-xl lg:hidden">
        <div className="mx-auto flex max-w-xl items-center justify-between px-3 py-2">
          {NAV.map(({ id, short, icon: Icon }) => (
            <button key={id} onClick={() => go(id)} aria-label={short}
              className={cn("flex cursor-pointer flex-col items-center gap-1 px-1.5 py-1", screen === id ? "text-ink" : "text-mute")}>
              <span className={cn("grid size-9 place-items-center rounded-[3px]", screen === id && "bg-primary text-on-primary")}>
                <Icon className="size-[18px]" />
              </span>
              <span className="text-[9.5px] font-bold uppercase tracking-[0.1em]">{short}</span>
            </button>
          ))}
        </div>
      </nav>

      {toast && (
        <div
          role="status"
          className={cn(
            "fixed bottom-24 right-5 z-50 max-w-md rounded-2xl px-5 py-3.5 text-sm font-medium shadow-2xl lg:bottom-6",
            toast.kind === "ok" ? "bg-accent-solid text-white" : "bg-bad-solid text-white",
          )}
        >
          {toast.msg}
        </div>
      )}
    </Ctx.Provider>
  );
}
