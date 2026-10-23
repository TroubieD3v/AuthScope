import { ChevronDown, ChevronRight, FileUp, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Method } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select, Textarea, Toggle } from "@/components/ui/field";
import { useAction, useApp } from "@/ctx";
import { api, type Access, type Endpoint } from "@/lib/api";
import { PageHeader } from "./common";

const ACCESS: { v: Access; label: string; hint: string }[] = [
  { v: "public", label: "public", hint: "no authentication needed" },
  { v: "authenticated", label: "authenticated", hint: "any logged-in identity" },
  { v: "owner", label: "owner", hint: "only the object's owner (+ allowed roles)" },
  { v: "tenant", label: "tenant", hint: "identities of the object's tenant (+ allowed roles)" },
  { v: "roles", label: "roles", hint: "only the listed roles (admin functions)" },
];

export function Explorer() {
  const { project, reload, notify } = useApp();
  const act = useAction();
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [specUrl, setSpecUrl] = useState("");
  const [specText, setSpecText] = useState("");
  const [target, setTarget] = useState({ base_url: project.target.base_url, hosts: project.target.allowed_hosts.join(", ") });
  const [manual, setManual] = useState({ method: "GET", path: "/api/" });
  const [warnings, setWarnings] = useState<string[]>([]);

  const saveTarget = () => act(async () => {
    await api.saveProject(project.id, {
      ...project,
      target: { ...project.target, base_url: target.base_url, allowed_hosts: target.hosts.split(",").map((h) => h.trim()).filter(Boolean) },
    });
    await reload();
  }, "Target saved");

  const doImport = async (body: { url?: string; content?: string }) => {
    const r = await act(async () => {
      const res = await api.importSpec(project.id, body);
      await reload();
      return res;
    });
    if (r) { setWarnings(r.warnings); notify(`${r.format}: ${r.added} new, ${r.updated} updated endpoints`); }
  };

  const endpoints = project.endpoints.filter((e) =>
    (e.method + " " + e.path + " " + (e.summary ?? "") + " " + e.tags.join(" ")).toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="space-y-6">
      <PageHeader title="API Explorer" hint="Target, OpenAPI import and the endpoint inventory with its access rules." />

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Target" hint="The engine only contacts hosts in this list." />
          <CardBody className="space-y-3">
            <Field label="Base URL"><Input value={target.base_url} onChange={(e) => setTarget({ ...target, base_url: e.target.value })} /></Field>
            <Field label="Allowed hosts" hint="Comma separated, no wildcards. host:port restricts the port."><Input value={target.hosts} onChange={(e) => setTarget({ ...target, hosts: e.target.value })} /></Field>
            <Button variant="secondary" size="sm" onClick={saveTarget}><Save className="size-3.5" /> Save target</Button>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Import OpenAPI / Swagger / Postman" hint="OpenAPI JSON/YAML or a Postman v2 collection. URLs are fetched only from allowed hosts." />
          <CardBody className="space-y-3">
            <div className="flex gap-2">
              <Input placeholder={`${project.target.base_url}/openapi.json`} value={specUrl} onChange={(e) => setSpecUrl(e.target.value)} />
              <Button variant="secondary" disabled={!specUrl} onClick={() => doImport({ url: specUrl })}>Fetch</Button>
            </div>
            <Textarea rows={2} placeholder="...or paste a spec / collection here" value={specText} onChange={(e) => setSpecText(e.target.value)} />
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={!specText.trim()} onClick={() => doImport({ content: specText })}>Import pasted</Button>
              <label className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md border border-line bg-panel2 px-2.5 text-xs hover:bg-[#1b2735]">
                <FileUp className="size-3.5" /> From file
                <input type="file" hidden accept=".json,.yaml,.yml" onChange={async (e) => { const f = e.target.files?.[0]; if (f) doImport({ content: await f.text() }); e.target.value = ""; }} />
              </label>
            </div>
            {warnings.map((w) => <p key={w} className="text-xs text-warn">{w}</p>)}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title={`Endpoints (${project.endpoints.length})`}
          hint="OpenAPI cannot say who owns what - confirm the inferred access rules (marked 'inferred')."
          actions={<Input className="h-8 w-56" placeholder="Filter..." value={filter} onChange={(e) => setFilter(e.target.value)} />} />
        <div className="divide-y divide-line">
          {endpoints.length === 0 && <p className="px-5 py-6 text-sm text-mute">No endpoints yet - import a spec or add one below.</p>}
          {endpoints.map((ep) => {
            const key = `${ep.method} ${ep.path}`;
            return (
              <div key={key}>
                <button onClick={() => setOpen(open === key ? null : key)} className="flex w-full cursor-pointer items-center gap-3 px-5 py-2.5 text-left hover:bg-panel2/50">
                  {open === key ? <ChevronDown className="size-4 text-mute" /> : <ChevronRight className="size-4 text-mute" />}
                  <Method m={ep.method} />
                  <span className={`font-mono text-[13px] ${ep.enabled ? "" : "text-mute line-through"}`}>{ep.path}</span>
                  <span className="flex-1 truncate text-xs text-mute">{ep.summary}</span>
                  {ep.restricted_fields.length > 0 && <Badge tone="info">{ep.restricted_fields.length} restricted fields</Badge>}
                  {ep.list_of && <Badge>list of {ep.list_of}</Badge>}
                  <Badge tone={ep.access === "public" ? "warn" : ep.access === "roles" ? "bad" : "accent"}>
                    {ep.access}{ep.allow_roles.length ? `: ${ep.allow_roles.join(",")}` : ""}
                  </Badge>
                  {ep.inferred && <Badge>inferred</Badge>}
                </button>
                {open === key && <EndpointEditor ep={ep} onDone={() => { setOpen(null); reload(); }} />}
              </div>
            );
          })}
        </div>
        <div className="flex items-end gap-2 border-t border-line p-4">
          <Field label="Method"><Select className="w-28" value={manual.method} onChange={(e) => setManual({ ...manual, method: e.target.value })}>
            {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => <option key={m}>{m}</option>)}</Select></Field>
          <Field label="Path" className="flex-1"><Input className="font-mono" value={manual.path} onChange={(e) => setManual({ ...manual, path: e.target.value })} placeholder="/api/orders/{order_id}" /></Field>
          <Button variant="secondary" onClick={() => act(async () => {
            await api.putEndpoint(project.id, blank(manual.method, manual.path)); await reload(); setOpen(`${manual.method} ${manual.path}`);
          }, "Endpoint added")}><Plus className="size-4" /> Add manually</Button>
        </div>
      </Card>
    </div>
  );
}

const blank = (method: string, path: string): Endpoint => ({
  method, path, summary: null, tags: [], access: "authenticated", allow_roles: [], resource_type: null, path_param: null,
  list_of: null, param_types: {}, restricted_fields: [], params: {}, query: {}, body: null, enabled: true, source: "manual", inferred: false,
});

function EndpointEditor({ ep, onDone }: { ep: Endpoint; onDone: () => void }) {
  const { project } = useApp();
  const act = useAction();
  const [d, setD] = useState<Endpoint>(ep);
  const [body, setBody] = useState(ep.body ? JSON.stringify(ep.body, null, 2) : "");
  const types = [...new Set(project.resources.map((r) => r.type))];

  const save = () => act(async () => {
    let parsed: unknown = null;
    if (body.trim()) parsed = JSON.parse(body);
    await api.putEndpoint(project.id, { ...d, body: parsed });
    onDone();
  }, "Endpoint saved");

  return (
    <div className="grid grid-cols-3 gap-4 bg-panel2/40 px-5 py-4">
      <Field label="Access rule" hint={ACCESS.find((a) => a.v === d.access)?.hint}>
        <Select value={d.access} onChange={(e) => setD({ ...d, access: e.target.value as Access })}>
          {ACCESS.map((a) => <option key={a.v} value={a.v}>{a.label}</option>)}</Select>
      </Field>
      <Field label="Allowed roles" hint="Comma separated (e.g. admin)">
        <Input value={d.allow_roles.join(", ")} onChange={(e) => setD({ ...d, allow_roles: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
      </Field>
      <div className="pt-5"><Toggle checked={d.enabled} onChange={(v) => setD({ ...d, enabled: v })} label="Include in tests" /></div>

      <Field label="Resource type" hint="Object type the path parameter refers to">
        <Input list="rtypes" value={d.resource_type ?? ""} onChange={(e) => setD({ ...d, resource_type: e.target.value || null })} />
        <datalist id="rtypes">{types.map((t) => <option key={t} value={t} />)}</datalist>
      </Field>
      <Field label="Lists objects of type" hint="For collection endpoints - checked for leaks">
        <Input value={d.list_of ?? ""} onChange={(e) => setD({ ...d, list_of: e.target.value || null })} />
      </Field>
      {ep.path.split("{").length > 2 && (
        <Field label="Path parameter types (nested paths, JSON)" hint='Which object type each parameter refers to, e.g. {"user_id":"user","order_id":"order"}' className="col-span-3">
          <Input className="font-mono text-xs" defaultValue={JSON.stringify(d.param_types)} onChange={(e) => { try { setD({ ...d, param_types: JSON.parse(e.target.value || "{}") }); } catch { /* typing */ } }} />
        </Field>
      )}
      <Field label="Fixed path params (JSON)" hint='Values for params that are not resources, e.g. {"version":"v1"}'>
        <Input className="font-mono text-xs" value={JSON.stringify(d.params)} onChange={(e) => { try { setD({ ...d, params: JSON.parse(e.target.value || "{}") }); } catch { /* typing */ } }} />
      </Field>

      <div className="col-span-3">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-medium text-mute">Restricted response fields (BOPLA)</span>
          <Button size="sm" variant="ghost" onClick={() => setD({ ...d, restricted_fields: [...d.restricted_fields, { name: "", roles: ["admin"], owner_can_see: false }] })}><Plus className="size-3" /> field</Button>
        </div>
        {d.restricted_fields.map((f, i) => (
          <div key={i} className="mb-1.5 flex items-center gap-2">
            <Input className="w-56 font-mono" placeholder="internalNotes" value={f.name} onChange={(e) => setD({ ...d, restricted_fields: d.restricted_fields.map((x, j) => j === i ? { ...x, name: e.target.value } : x) })} />
            <Input className="w-48" placeholder="roles allowed to see" value={f.roles.join(", ")} onChange={(e) => setD({ ...d, restricted_fields: d.restricted_fields.map((x, j) => j === i ? { ...x, roles: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) } : x) })} />
            <Toggle checked={f.owner_can_see} onChange={(v) => setD({ ...d, restricted_fields: d.restricted_fields.map((x, j) => j === i ? { ...x, owner_can_see: v } : x) })} label="owner can see" />
            <Button size="icon" variant="ghost" onClick={() => setD({ ...d, restricted_fields: d.restricted_fields.filter((_, j) => j !== i) })}><Trash2 className="size-3.5" /></Button>
          </div>
        ))}
      </div>

      {d.method !== "GET" && (
        <Field label="Request body (JSON) used for state-changing tests" className="col-span-3">
          <Textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
      )}
      <div className="col-span-3 flex gap-2">
        <Button size="sm" onClick={save}><Save className="size-3.5" /> Save endpoint</Button>
        <Button size="sm" variant="danger" onClick={() => confirm("Remove this endpoint?") && act(async () => { await api.deleteEndpoint(project.id, `${ep.method} ${ep.path}`); onDone(); })}><Trash2 className="size-3.5" /> Remove</Button>
      </div>
    </div>
  );
}
