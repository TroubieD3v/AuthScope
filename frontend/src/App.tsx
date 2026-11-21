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

  if (projects === null) return <div className="grid h-screen place-items-center text-mute">Loading...</div>;
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
  const t = project.target;

  return (
    <Ctx.Provider value={{ project, reload, go, notify, focusRun, setFocusRun }}>
      {/* Tool tabs */}
      <header className="sticky top-0 z-40 flex h-9 items-stretch border-b border-line bg-chrome">
        <div className="flex items-center border-r border-line px-3"><Logo /></div>
        <nav className="hidden items-stretch lg:flex">
          {NAV.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => go(id)}
              className={cn(
                "cursor-pointer whitespace-nowrap px-3.5 text-[12.5px] transition-colors",
                screen === id ? "bg-bg text-ink shadow-[inset_0_-2px_0_var(--accent)]" : "text-mute hover:bg-panel2/60 hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1.5 px-2">
          <select
            value={pid}
            aria-label="Project"
            onChange={(e) => e.target.value === "__new" ? setCreating(true) : setPid(e.target.value)}
            className="hidden h-7 max-w-[16rem] cursor-pointer border border-line bg-bg px-2 text-xs sm:block"
          >
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            <option value="__new">+ New project...</option>
          </select>
          <ThemeToggle />
        </div>
      </header>

      <main className="min-w-0 px-4 pb-24 pt-3 lg:pb-12">
        <View />
      </main>

      {/* Status bar */}
      <footer className="fixed inset-x-0 bottom-0 z-40 hidden h-6 items-center gap-5 border-t border-line bg-chrome px-3 text-[11.5px] text-mute lg:flex">
        <span>project <b className="font-medium text-ink">{project.name}</b></span>
        <span>target <span className="font-mono text-ink">{t.base_url}</span></span>
        <span>{t.allowed_hosts.length} host{t.allowed_hosts.length === 1 ? "" : "s"} allowed</span>
        <span>{t.rate_limit_rps} req/s · budget {t.max_requests}</span>
        <span className={t.allow_mutating ? "text-warn" : ""}>{t.allow_mutating ? "state-changing requests on" : "read-only"}</span>
        <button onClick={deleteProject} className="ml-auto flex cursor-pointer items-center gap-1 hover:text-bad">
          <Trash2 className="size-3" /> Delete project
        </button>
      </footer>

      {/* Mobile tool switcher */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-chrome lg:hidden">
        <div className="mx-auto flex max-w-xl items-center justify-between px-2 py-1">
          {NAV.map(({ id, short, icon: Icon }) => (
            <button key={id} onClick={() => go(id)} aria-label={short}
              className={cn("flex cursor-pointer flex-col items-center gap-0.5 px-1.5 py-1", screen === id ? "text-accent" : "text-mute")}>
              <Icon className="size-[17px]" />
              <span className="text-[10px]">{short}</span>
            </button>
          ))}
        </div>
      </nav>

      {toast && (
        <div
          role="status"
          className={cn(
            "fixed bottom-20 right-3 z-50 max-w-md border border-line bg-panel px-3 py-2 text-[12.5px] lg:bottom-9",
            toast.kind === "ok" ? "shadow-[inset_3px_0_0_var(--accent)]" : "text-bad shadow-[inset_3px_0_0_var(--bad)]",
          )}
        >
          {toast.msg}
        </div>
      )}
    </Ctx.Provider>
  );
}
