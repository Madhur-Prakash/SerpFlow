/**
 * Settings.
 *
 * The credential screen is the one that matters most here: the upstream key is
 * accepted once, encrypted with a per-credential data key, and then only ever
 * shown as a non-reversible fingerprint. Nothing on this page can display it
 * again, because no response from the server contains it.
 */

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Bell,
  Building2,
  CheckCircle,
  Copy,
  ExternalLink,
  Key,
  KeyRound,
  Lock,
  Plus,
  RefreshCw,
  Shield,
  Terminal,
  Trash2,
  Users,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { listVariants } from "@/animations";
import { EmptyState, ErrorMessage, PageHeader, Section } from "@/components/shared";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  Field,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Switch,
  Tooltip,
} from "@/components/ui";
import {
  useApiKeys,
  useCredentialProviders,
  useCredentials,
  useMembers,
  useProjects,
  useSessions,
} from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";
import { PERMISSIONS, useSession } from "@/stores/session";
import { RolesSettings } from "@/pages/settings/RolesSettings";
import type { Credential, CredentialProvider, Project } from "@/types/api";

/**
 * Absolute, deliberately.
 *
 * These links live inside a nested `<Routes>` mounted at `settings/*`, where a
 * relative `to="members"` resolves against the current URL rather than the
 * settings root: from /app/settings/organization it produced
 * /app/settings/organization/members, which matches no child, so the layout
 * never rendered and the page came up blank.
 */
const SETTINGS_ROOT = "/app/settings";

const TABS = [
  { to: SETTINGS_ROOT + "/organization", label: "Organization", icon: Building2 },
  { to: SETTINGS_ROOT + "/members", label: "Members", icon: Users },
  { to: SETTINGS_ROOT + "/roles", label: "Roles", icon: Shield },
  { to: SETTINGS_ROOT + "/projects", label: "Projects", icon: Terminal },
  { to: SETTINGS_ROOT + "/api-keys", label: "API keys", icon: Key },
  { to: SETTINGS_ROOT + "/credentials", label: "Credentials", icon: Shield },
  { to: SETTINGS_ROOT + "/security", label: "Security", icon: Lock },
  { to: SETTINGS_ROOT + "/notifications", label: "Notifications", icon: Bell },
];

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        icon={Terminal}
        description="Organization, members, projects, keys, credentials and policy."
      />
      <div className="grid gap-6 lg:grid-cols-[180px_minmax(0,1fr)]">
        <nav className="space-y-0.5">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 py-1.5 text-[13px] transition-colors",
                  isActive
                    ? "bg-surface-raised text-ink"
                    : "text-ink-muted hover:bg-surface hover:text-ink",
                )
              }
            >
              <tab.icon className="size-3.5" />
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

export function SettingsRoutes() {
  return (
    <Routes>
      <Route element={<SettingsPage />}>
        <Route index element={<Navigate to="organization" replace />} />
        <Route path="organization" element={<OrganizationSettings />} />
        <Route path="members" element={<MembersSettings />} />
        <Route path="roles" element={<RolesSettings />} />
        <Route path="projects" element={<ProjectsSettings />} />
        <Route path="api-keys" element={<ApiKeysSettings />} />
        <Route path="credentials" element={<CredentialsSettings />} />
        <Route path="security" element={<SecuritySettings />} />
        <Route path="notifications" element={<NotificationsSettings />} />
        {/* Anything else under settings returns to the first tab rather than
            rendering an empty panel. */}
        <Route path="*" element={<Navigate to={SETTINGS_ROOT + "/organization"} replace />} />
      </Route>
    </Routes>
  );
}

// ------------------------------------------------------- organization
function OrganizationSettings() {
  const { me, can } = useSession();
  const canEdit = can(PERMISSIONS.orgUpdate);
  const [saving, setSaving] = React.useState(false);

  async function update(patch: Record<string, unknown>) {
    setSaving(true);
    try {
      await api.updateOrganization(patch);
      toast.success("Organization updated");
    } catch (error) {
      toast.error("Could not update", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      <Card>
        <CardHeader title="Organization" icon={Building2} />
        <CardBody className="space-y-4">
          <Field label="Name">
            <Input
              defaultValue={me?.organization?.name}
              disabled={!canEdit || saving}
              onBlur={(event) => update({ name: event.target.value })}
            />
          </Field>
          <Field label="Slug">
            <Input defaultValue={me?.organization?.slug} disabled className="mono" />
          </Field>
          <Field
            label="Cache scope"
            hint="Organization scope lets projects share cached results. That crosses a billing and a data boundary, so each project still has to opt in."
          >
            <Select
              defaultValue={me?.organization?.cache_scope ?? "project"}
              disabled={!canEdit || saving}
              onValueChange={(value) => update({ cache_scope: value })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="project">Project isolated</SelectItem>
                <SelectItem value="organization">Organization shared</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </CardBody>
      </Card>
    </motion.div>
  );
}

// ------------------------------------------------------------ members
/** The organization's own roles, for the pickers. Empty when none are defined. */
function useCustomRoles() {
  const [roles, setRoles] = React.useState<{ slug: string; name: string }[]>([]);
  React.useEffect(() => {
    api
      .roles()
      .then((page) => setRoles(page.items ?? []))
      // A member manager without role:read still gets the built-in options.
      .catch(() => setRoles([]));
  }, []);
  return roles;
}

function MembersSettings() {
  const customRoles = useCustomRoles();
  const { can, me } = useSession();
  const members = useMembers();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("developer");
  const canWrite = can(PERMISSIONS.memberWrite);

  async function invite() {
    try {
      await api.inviteMember({ email, role });
      toast.success("Member added");
      setEmail("");
      members.refetch();
    } catch (error) {
      toast.error("Could not add the member", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (members.isError) return <ErrorMessage error={members.error} />;

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      {canWrite ? (
        <Card>
          <CardHeader
            title="Add a member"
            icon={Users}
            description="The person must already have a SerpFlow account."
          />
          <CardBody>
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Email" className="min-w-56 flex-1">
                <Input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="colleague@company.com"
                />
              </Field>
              <Field label="Role" className="w-40">
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="analyst">Analyst</SelectItem>
                    <SelectItem value="developer">Developer</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                    {me?.role === "owner" ? (
                      <SelectItem value="owner">Owner</SelectItem>
                    ) : null}
                    {customRoles.map((custom) => (
                      <SelectItem key={custom.slug} value={custom.slug}>
                        {custom.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Button variant="primary" onClick={invite} disabled={!email}>
                <Plus />
                Add
              </Button>
            </div>
            <p className="mt-3 text-[12px] leading-relaxed text-ink-subtle text-pretty">
              An analyst can plan but not execute. Planning calls a language model rather than
              SerpApi, so it spends nothing, which is what makes the role useful rather than
              decorative.
            </p>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Members" icon={Users} />
        {members.isLoading ? (
          <CardBody className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-11" />
            ))}
          </CardBody>
        ) : members.data?.length ? (
          <ul className="divide-y divide-line">
            {members.data.map((member) => (
              <li key={member.id} className="flex items-center gap-3 px-4 py-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full border border-line bg-surface-raised text-[11px] font-semibold text-ink-muted">
                  {(member.full_name || member.email).slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-ink">
                    {member.full_name || member.email}
                  </p>
                  <p className="truncate text-[11px] text-ink-subtle">{member.email}</p>
                </div>
                {canWrite ? (
                  <Select
                    defaultValue={member.role}
                    onValueChange={async (value) => {
                      try {
                        await api.updateMember(member.id, value);
                        toast.success("Role updated");
                        members.refetch();
                      } catch (error) {
                        toast.error("Could not change the role", {
                          description:
                            error instanceof Error ? error.message : String(error),
                        });
                      }
                    }}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="analyst">Analyst</SelectItem>
                      <SelectItem value="developer">Developer</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                      <SelectItem value="owner">Owner</SelectItem>
                      {customRoles.map((custom) => (
                        <SelectItem key={custom.slug} value={custom.slug}>
                          {custom.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge tone="outline">{member.role}</Badge>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <CardBody>
            <EmptyState
              icon={Users}
              title="No members"
              description="Members belong to the organization and inherit a role across every project unless a project override narrows it."
            />
          </CardBody>
        )}
      </Card>
    </motion.div>
  );
}

// ----------------------------------------------------------- projects
function ProjectsSettings() {
  const projects = useProjects();
  const { can } = useSession();
  const [name, setName] = React.useState("");
  const canWrite = can(PERMISSIONS.projectWrite);

  async function create() {
    try {
      await api.createProject({ name });
      toast.success("Project created");
      setName("");
      projects.refetch();
    } catch (error) {
      toast.error("Could not create the project", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      {canWrite ? (
        <Card>
          <CardHeader title="New project" icon={Terminal} />
          <CardBody>
            <div className="flex items-end gap-2">
              <Field label="Name" className="flex-1">
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Market Watch"
                />
              </Field>
              <Button variant="primary" onClick={create} disabled={!name}>
                <Plus />
                Create
              </Button>
            </div>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Projects"
          icon={Terminal}
          description="Each project gets its own six-character key prefix, cache partition, budget and policy."
        />
        {projects.data?.length ? (
          <ul className="divide-y divide-line">
            {projects.data.map((project) => (
              <li key={project.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-medium text-ink">{project.name}</span>
                  <Badge tone="outline" className="mono">
                    {project.key_prefix}
                  </Badge>
                  {project.shared_cache_enabled ? (
                    <Tooltip content="This project participates in the organization-level shared cache.">
                      <Badge tone="caution">shared cache</Badge>
                    </Tooltip>
                  ) : null}
                  {project.engine_denylist.length ? (
                    <Badge tone="outline" className="mono">
                      {project.engine_denylist.length} denied
                    </Badge>
                  ) : null}
                </div>
                {project.description ? (
                  <p className="mt-1 text-[12px] text-ink-subtle text-pretty">
                    {project.description}
                  </p>
                ) : null}
                <ExecutionModeField
                  project={project}
                  canWrite={canWrite}
                  onSaved={() => projects.refetch()}
                />
              </li>
            ))}
          </ul>
        ) : (
          <CardBody>
            <Skeleton className="h-20" />
          </CardBody>
        )}
      </Card>
    </motion.div>
  );
}

/**
 * The project's execution mode.
 *
 * Worth stating plainly in the interface rather than in a tooltip: two of
 * these three spend real money on the organization's own SerpApi account, and
 * the person setting it is often not the person who will run the searches.
 */
function ExecutionModeField({
  project,
  canWrite,
  onSaved,
}: {
  project: Project;
  canWrite: boolean;
  onSaved: () => void;
}) {
  const [saving, setSaving] = React.useState(false);
  // Radix reserves "" for "nothing selected", so the inherit case needs a
  // sentinel of its own or the trigger renders blank. The API's own way of
  // saying "clear this" is "", since null means "leave this field alone" in a
  // PATCH, so the two are translated at the boundary.
  const INHERIT = "inherit";
  const current = project.execution_mode || INHERIT;

  async function save(choice: string) {
    const value = choice === INHERIT ? "" : choice;
    setSaving(true);
    try {
      await api.updateProject(project.id, { execution_mode: value } as Partial<Project>);
      toast.success(
        value
          ? "This project now runs in " + value + " mode."
          : "This project follows the instance default again.",
      );
      onSaved();
    } catch (error) {
      toast.error("Could not change the execution mode", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-subtle">
        Execution mode
      </span>
      {canWrite ? (
        <Select value={current} onValueChange={save} disabled={saving}>
          <SelectTrigger className="h-7 w-[11rem] text-[12px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={INHERIT}>Instance default</SelectItem>
            <SelectItem value="replay">replay</SelectItem>
            <SelectItem value="live">live</SelectItem>
            <SelectItem value="record">record</SelectItem>
          </SelectContent>
        </Select>
      ) : (
        <Badge tone="outline" className="mono">
          {current === INHERIT ? "instance default" : current}
        </Badge>
      )}
      {current === "live" || current === "record" ? (
        <span className="text-[11.5px] text-caution">
          {current === "record"
            ? "Spends credits on your SerpApi account, and saves cassettes."
            : "Spends credits on your SerpApi account."}
        </span>
      ) : (
        <span className="text-[11.5px] text-ink-subtle">
          {current === "replay"
            ? "Served from recorded cassettes. Never reaches the network."
            : "Follows SERPFLOW_MODE. A test API key always overrides this."}
        </span>
      )}
    </div>
  );
}

// ----------------------------------------------------------- API keys
function ApiKeysSettings() {
  const { project, can } = useSession();
  const keys = useApiKeys();
  const [createOpen, setCreateOpen] = React.useState(false);
  const [minted, setMinted] = React.useState<{ plaintext: string; name: string } | null>(null);
  const canWrite = can(PERMISSIONS.keyWrite) || can(PERMISSIONS.keyProjectWrite);

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      <Card>
        <CardHeader
          title="API keys"
          icon={Key}
          description="Format sf_<env>_<project prefix>_<secret>. Stored as an HMAC-SHA256 hash under a server-side pepper, never as plaintext."
          action={
            canWrite ? (
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus />
                New key
              </Button>
            ) : null
          }
        />
        <CardBody className="space-y-3">
          <Alert tone="accent" icon={CheckCircle} title="Test keys cost nothing">
            A key issued in the test environment always routes to the deterministic mock,
            whatever SERPFLOW_MODE says, and consumes zero SerpApi credits. That precedence is
            absolute, so you can integrate fully before connecting a paid account.
          </Alert>

          {keys.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-14" />
              ))}
            </div>
          ) : keys.data?.items.length ? (
            <ul className="divide-y divide-line">
              {keys.data.items.map((key) => (
                <li key={key.id} className="flex flex-wrap items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] text-ink">{key.name}</span>
                      <Badge tone={key.environment === "test" ? "accent" : "warm"}>
                        {key.environment}
                      </Badge>
                      <Badge tone="outline">{key.role}</Badge>
                      {key.is_service_principal ? (
                        <Tooltip content="Machine identity. Every execution resolves a service session with its own cap and audit trail.">
                          <Badge tone="replay">service principal</Badge>
                        </Tooltip>
                      ) : null}
                      {key.revoked_at ? <Badge tone="danger">revoked</Badge> : null}
                    </div>
                    <p className="mono mt-1 text-[12px] text-ink-subtle">{key.display}</p>
                    <p className="mt-0.5 text-[11px] text-ink-subtle">
                      {key.last_used_at
                        ? "last used " +
                          fmt.ago(key.last_used_at) +
                          (key.last_used_ip ? " from " + key.last_used_ip : "") +
                          " - " +
                          key.use_count +
                          " uses"
                        : "never used"}
                    </p>
                  </div>
                  {canWrite && !key.revoked_at ? (
                    <div className="flex gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={async () => {
                          try {
                            const result = await api.rotateKey(key.id, 60);
                            setMinted({
                              plaintext: result.plaintext,
                              name: result.key.name,
                            });
                            keys.refetch();
                          } catch (error) {
                            toast.error("Rotation failed", {
                              description:
                                error instanceof Error ? error.message : String(error),
                            });
                          }
                        }}
                      >
                        <RefreshCw />
                        Rotate
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={async () => {
                          try {
                            const result = await api.revokeKey(key.id, "revoked from settings");
                            toast.success(result.message);
                            keys.refetch();
                          } catch (error) {
                            toast.error("Revocation failed", {
                              description:
                                error instanceof Error ? error.message : String(error),
                            });
                          }
                        }}
                      >
                        <Trash2 />
                        Revoke
                      </Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Key}
              title="No API keys"
              description="An API key is how your code authenticates to SerpFlow. It is separate from the SerpApi credential SerpFlow spends on your behalf."
            />
          )}
        </CardBody>
      </Card>

      <CreateKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        projectId={project?.id}
        onCreated={(result) => {
          setMinted({ plaintext: result.plaintext, name: result.key.name });
          keys.refetch();
        }}
      />

      <Dialog open={Boolean(minted)} onOpenChange={(open) => !open && setMinted(null)}>
        <DialogContent>
          <DialogHeader
            title="Copy this key now"
            description="It is stored only as an HMAC hash and cannot be shown again."
          />
          <div className="px-5 py-4">
            <div className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5">
              <code className="mono min-w-0 flex-1 break-all text-[12px] text-ink">
                {minted?.plaintext}
              </code>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={async () => {
                  await navigator.clipboard.writeText(minted?.plaintext ?? "");
                  toast.success("Copied");
                }}
                aria-label="Copy key"
              >
                <Copy />
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button variant="primary" size="sm" onClick={() => setMinted(null)}>
              I have copied it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}

function CreateKeyDialog({
  open,
  onOpenChange,
  projectId,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId?: string;
  onCreated: (result: { plaintext: string; key: { name: string } }) => void;
}) {
  const [name, setName] = React.useState("");
  const [environment, setEnvironment] = React.useState("test");
  const [role, setRole] = React.useState("developer");
  const [servicePrincipal, setServicePrincipal] = React.useState(false);
  const [sessionCap, setSessionCap] = React.useState("20");
  const [saving, setSaving] = React.useState(false);

  async function submit() {
    if (!projectId) return;
    setSaving(true);
    try {
      const result = await api.createKey(projectId, {
        name,
        environment,
        role: servicePrincipal ? "service" : role,
        is_service_principal: servicePrincipal,
        session_cap: servicePrincipal ? Number(sessionCap) : null,
      });
      onCreated(result);
      onOpenChange(false);
      setName("");
    } catch (error) {
      toast.error("Could not create the key", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader title="New API key" />
        <div className="space-y-4 px-5 py-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Production ingest"
            />
          </Field>
          <Field
            label="Environment"
            hint={
              environment === "test"
                ? "Always routes to the deterministic mock and spends zero SerpApi credits."
                : "Honours SERPFLOW_MODE and needs an upstream credential attached."
            }
          >
            <Select value={environment} onValueChange={setEnvironment}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="test">Test</SelectItem>
                <SelectItem value="live">Live</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          {!servicePrincipal ? (
            <Field label="Role" hint="A key can never grant more than its creator holds.">
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="analyst">Analyst - plan only</SelectItem>
                  <SelectItem value="developer">Developer - plan and execute</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          ) : null}
          <div className="flex items-start justify-between gap-4 rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5">
            <div>
              <p className="text-[13px] font-medium text-ink">Service principal</p>
              <p className="mt-0.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">
                For MCP and agent callers. Every execution resolves a session with its own cap
                and audit trail, rather than treating the agent as a human with a shared key.
              </p>
            </div>
            <Switch checked={servicePrincipal} onCheckedChange={setServicePrincipal} />
          </div>
          {servicePrincipal ? (
            <Field label="Session cap" hint="Credits one agent session may spend.">
              <Input
                type="number"
                min="1"
                value={sessionCap}
                onChange={(event) => setSessionCap(event.target.value)}
              />
            </Field>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={submit} disabled={!name || saving}>
            <Key />
            Create key
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// -------------------------------------------------------- credentials
function CredentialsSettings() {
  const credentials = useCredentials();
  const providers = useCredentialProviders();
  const { can } = useSession();
  const [adding, setAdding] = React.useState<CredentialProvider | null>(null);
  const canWrite = can(PERMISSIONS.credentialWrite);
  const canRotate = can(PERMISSIONS.credentialRotate);

  // Grouped by provider so each key sits under the service it belongs to. The
  // provider list comes from the API rather than being hardcoded here, so a
  // provider added to the backend registry appears without a frontend change.
  const byProvider = React.useMemo(() => {
    const map = new Map<string, Credential[]>();
    for (const credential of credentials.data ?? []) {
      const list = map.get(credential.provider) ?? [];
      list.push(credential);
      map.set(credential.provider, list);
    }
    return map;
  }, [credentials.data]);

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      <Card data-card>
        <CardHeader
          title="Your keys"
          icon={KeyRound}
          description="SerpFlow runs on keys you bring. Searches are billed to your SerpApi account and planning to your Groq account - this platform holds no keys of its own that your work could fall back to."
        />
        <CardBody>
          <Alert tone="accent" icon={Lock} title="Encrypted on arrival, never returned">
            Each key gets its own random data key, itself encrypted under a key-encryption key.
            Only the fingerprint - sha256 of the key, first eight characters - is ever shown, and
            no API response schema has a field that could carry the secret.
          </Alert>
        </CardBody>
      </Card>

      {providers.isLoading ? (
        <Skeleton className="h-40" />
      ) : (
        (providers.data ?? []).map((provider) => {
          const rows = byProvider.get(provider.id) ?? [];
          const active = rows.filter((row) => !row.revoked_at);
          return (
            <Card key={provider.id} data-card>
              <CardHeader
                title={provider.label}
                icon={Shield}
                description={provider.purpose}
                action={
                  canWrite ? (
                    <Button variant="primary" size="sm" onClick={() => setAdding(provider)}>
                      <Plus />
                      Add key
                    </Button>
                  ) : null
                }
              />
              <CardBody className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  {active.length ? (
                    <Badge tone="warm">
                      <CheckCircle />
                      configured
                    </Badge>
                  ) : (
                    <Badge tone={provider.required ? "danger" : "outline"}>
                      {provider.required ? "required" : "optional"}
                    </Badge>
                  )}
                  <a
                    href={provider.console_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 text-[12px] text-accent underline-offset-2 hover:underline"
                  >
                    <ExternalLink className="size-3.5" />
                    Get a {provider.label} key
                  </a>
                </div>

                {active.length ? null : (
                  <p className="text-[12.5px] leading-relaxed text-ink-muted text-pretty">
                    <span className="text-ink-subtle">Without one: </span>
                    {provider.absent_behaviour}
                  </p>
                )}

                {credentials.isLoading ? (
                  <Skeleton className="h-16" />
                ) : rows.length ? (
                  <ul className="divide-y divide-line">
                    {rows.map((credential) => (
                      <li key={credential.id} className="flex flex-wrap items-center gap-3 py-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[13px] text-ink">{credential.name}</span>
                            <Badge tone="outline" className="mono">
                              {credential.display}
                            </Badge>
                            {credential.validation_status === "valid" ? (
                              <Badge tone="warm">
                                <CheckCircle />
                                validated
                              </Badge>
                            ) : credential.validation_status === "failed" ? (
                              <Tooltip content={credential.validation_error ?? ""}>
                                <Badge tone="danger">
                                  <XCircle />
                                  failed
                                </Badge>
                              </Tooltip>
                            ) : (
                              <Badge tone="outline">pending</Badge>
                            )}
                            {credential.revoked_at ? <Badge tone="danger">revoked</Badge> : null}
                          </div>
                          <p className="mt-1 text-[11px] text-ink-subtle">
                            added {fmt.datetime(credential.created_at)}
                            {credential.last_validated_at
                              ? " - validated " + fmt.ago(credential.last_validated_at)
                              : ""}
                            {credential.upstream_searches_left !== null &&
                            credential.upstream_searches_left !== undefined
                              ? " - " +
                                credential.upstream_searches_left +
                                " searches left on your account"
                              : ""}
                          </p>
                        </div>
                        {canWrite && !credential.revoked_at ? (
                          <div className="flex gap-1.5">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={async () => {
                                try {
                                  await api.validateCredential(credential.id);
                                  toast.success("Key validated");
                                  credentials.refetch();
                                  providers.refetch();
                                } catch (error) {
                                  toast.error("Validation failed", {
                                    description:
                                      error instanceof Error ? error.message : String(error),
                                  });
                                }
                              }}
                            >
                              <RefreshCw />
                              Validate
                            </Button>
                            {canRotate ? (
                              <Button
                                variant="danger"
                                size="sm"
                                onClick={async () => {
                                  try {
                                    const result = await api.revokeCredential(credential.id);
                                    toast.success(result.message);
                                    credentials.refetch();
                                    providers.refetch();
                                  } catch (error) {
                                    toast.error("Revocation failed", {
                                      description:
                                        error instanceof Error ? error.message : String(error),
                                    });
                                  }
                                }}
                              >
                                <Trash2 />
                                Revoke
                              </Button>
                            ) : null}
                          </div>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </CardBody>
            </Card>
          );
        })
      )}

      <AddCredentialDialog
        provider={adding}
        onOpenChange={(open) => !open && setAdding(null)}
        onCreated={() => {
          credentials.refetch();
          providers.refetch();
        }}
      />
    </motion.div>
  );
}

function AddCredentialDialog({
  provider,
  onOpenChange,
  onCreated,
}: {
  provider: CredentialProvider | null;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const [name, setName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [validateNow, setValidateNow] = React.useState(true);
  const [saving, setSaving] = React.useState(false);

  // Cleared whenever the dialog opens for a different provider, so a key typed
  // for one service cannot be submitted against another.
  React.useEffect(() => {
    if (provider) {
      setName("My " + provider.label + " account");
      setApiKey("");
    }
  }, [provider]);

  async function submit() {
    if (!provider) return;
    setSaving(true);
    try {
      await api.createCredential({
        name,
        api_key: apiKey,
        provider: provider.id,
        validate_now: validateNow,
        // The organization-default pointer belongs to SerpApi; every other
        // provider already resolves organization-wide.
        set_as_org_default: provider.id === "serpapi",
      });
      toast.success(provider.label + " key stored", {
        description: "Only its fingerprint is retrievable from now on.",
      });
      setApiKey("");
      onOpenChange(false);
      onCreated();
    } catch (error) {
      toast.error("Could not store the key", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={provider !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title={"Add your " + (provider?.label ?? "") + " key"}
          description={
            provider
              ? provider.purpose +
                " This is your own account's key, separate from the API keys your code uses to call SerpFlow."
              : ""
          }
        />
        <div className="space-y-4 px-5 py-4">
          <Field label="Name" hint="For your own reference.">
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field
            label={(provider?.label ?? "") + " key"}
            hint="Encrypted immediately. After this dialog closes there is no way to read it back."
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={provider?.key_hint ?? ""}
              className="mono"
              autoComplete="off"
            />
          </Field>
          {provider ? (
            <a
              href={provider.console_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 text-[12px] text-accent underline-offset-2 hover:underline"
            >
              <ExternalLink className="size-3.5" />
              Where to find it in the {provider.label} console
            </a>
          ) : null}
          <div className="flex items-center justify-between gap-4 rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5">
            <div>
              <p className="text-[13px] font-medium text-ink">Validate now</p>
              <p className="mt-0.5 text-[12px] text-ink-subtle text-pretty">
                One cheap call to prove the key works, before you depend on it. It spends
                nothing.
              </p>
            </div>
            <Switch checked={validateNow} onCheckedChange={setValidateNow} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={submit} disabled={!apiKey || saving}>
            <Shield />
            Store encrypted
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ----------------------------------------------------------- security
function SecuritySettings() {
  const sessions = useSessions();
  const navigate = useNavigate();
  const { logout } = useSession();

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      <Card>
        <CardHeader
          title="Active sessions"
          icon={Lock}
          description="Refresh tokens rotate on every use, so a stolen one stops working the moment the real session refreshes."
        />
        {sessions.isLoading ? (
          <CardBody>
            <Skeleton className="h-20" />
          </CardBody>
        ) : sessions.data?.length ? (
          <ul className="divide-y divide-line">
            {sessions.data.map((session) => (
              <li key={session.id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] text-ink">
                    {session.user_agent || "unknown client"}
                  </p>
                  <p className="mono mt-0.5 text-[11px] text-ink-subtle">
                    {session.ip || "no ip"} - started {fmt.ago(session.created_at)}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    await api.revokeSession(session.id);
                    toast.success("Session revoked");
                    sessions.refetch();
                  }}
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <CardBody>
            <EmptyState icon={Lock} title="No active sessions" description="Nothing to revoke." />
          </CardBody>
        )}
      </Card>

      <Card>
        <CardHeader title="Sign out everywhere" icon={AlertTriangle} />
        <CardBody>
          <Button
            variant="danger"
            size="sm"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Revoke every session
          </Button>
        </CardBody>
      </Card>
    </motion.div>
  );
}

// ------------------------------------------------------ notifications
/**
 * The label picker's "none of these" option.
 *
 * Not a label itself - it reveals the free-text box. Anything typed there is
 * accepted and renders with the generic template, so a custom label is a
 * first-class choice rather than a fallback the UI hides.
 */
const CUSTOM_LABEL = "__custom__";

type ChannelLabels = Awaited<ReturnType<typeof api.channelLabels>>;

function NotificationsSettings() {
  const { can } = useSession();
  const canWrite = can(PERMISSIONS.alertWrite);

  const [channels, setChannels] = React.useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [kind, setKind] = React.useState("email");
  const [name, setName] = React.useState("");
  const [target, setTarget] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  // The label picker. A preset selects a fixed email template; CUSTOM reveals
  // a free-text box, and anything typed there renders with the generic one.
  const [labels, setLabels] = React.useState<ChannelLabels | null>(null);
  const [labelChoice, setLabelChoice] = React.useState(CUSTOM_LABEL);

  const activeLabel = React.useMemo(
    () => labels?.presets.find((preset) => preset.value === labelChoice) ?? null,
    [labels, labelChoice],
  );

  const refresh = React.useCallback(async () => {
    const [rows, labelCatalogue] = await Promise.all([
      api.channels().catch(() => []),
      api.channelLabels().catch(() => null),
    ]);
    setChannels(Array.isArray(rows) ? rows : []);
    setLabels(labelCatalogue);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  async function add() {
    if (!target.trim()) {
      toast.error(kind === "email" ? "Enter an email address." : "Enter a URL.");
      return;
    }
    setSaving(true);
    try {
      // A preset sends its own label; CUSTOM sends whatever was typed.
      const label =
        labelChoice === CUSTOM_LABEL
          ? name.trim() || (kind === "email" ? "Email" : "Webhook")
          : labelChoice;
      await api.createChannel({ name: label, kind, target: target.trim() });
      toast.success("Channel added.");
      setName("");
      setTarget("");
      await refresh();
    } catch (error) {
      toast.error((error as { message?: string })?.message ?? "Could not add the channel.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteChannel(id);
      toast.success("Channel removed.");
      await refresh();
    } catch (error) {
      toast.error((error as { message?: string })?.message ?? "Could not remove the channel.");
    }
  }

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      <Card>
        <CardHeader
          title="Notification channels"
          icon={Bell}
          description="Where SerpFlow sends alerts. Add an email address or a webhook URL, and it will be told when a budget crosses its threshold or runs out, a run fails, routing accuracy regresses, a credential stops working, or the upstream quota diverges from what SerpFlow has recorded."
        />
        <CardBody>
          {canWrite ? (
            // `items-end` aligns the row on the inputs, which only works while
            // every Field is the same height. A `hint` renders *below* the
            // input, so the one carrying "Optional" pushed its own input up and
            // left the row ragged - the marker lives in the label instead.
            <div className="mb-4 flex flex-wrap items-end gap-2.5 rounded-[var(--radius-sm)] border border-line bg-surface-sunken p-3">
              <Field label="Type" className="w-36 shrink-0">
                <Select value={kind} onValueChange={setKind}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="email">Email</SelectItem>
                    <SelectItem value="webhook">Webhook</SelectItem>
                    <SelectItem value="slack">Slack</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Label" className="w-44 shrink-0">
                <Select value={labelChoice} onValueChange={setLabelChoice}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(labels?.presets ?? []).map((preset) => (
                      <SelectItem key={preset.slug} value={preset.value}>
                        {preset.value}
                      </SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_LABEL}>Custom...</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              {labelChoice === CUSTOM_LABEL ? (
                <Field label="Custom label" className="w-44 shrink-0">
                  <Input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder={kind === "email" ? "Growth squad" : "Ops webhook"}
                  />
                </Field>
              ) : null}
              <Field label={kind === "email" ? "Address" : "URL"} className="min-w-56 flex-1">
                <Input
                  value={target}
                  onChange={(event) => setTarget(event.target.value)}
                  placeholder={
                    kind === "email" ? "oncall@company.com" : "https://hooks.example.com/serpflow"
                  }
                />
              </Field>
              <Button
                variant="primary"
                onClick={add}
                disabled={saving || !target.trim()}
                className="shrink-0"
              >
                <Plus />
                Add channel
              </Button>

              {/* What the label actually does, at the point of choosing it.
                  Without this it reads as a name for your own reference. */}
              <p className="w-full text-[11.5px] leading-relaxed text-ink-subtle">
                {activeLabel
                  ? activeLabel.description +
                    (activeLabel.urgent ? " Subject is marked urgent." : "") +
                    (activeLabel.includes_detail
                      ? ""
                      : " Identifiers are left out of the message.")
                  : labels
                    ? labels.custom.description
                    : "The label decides how an alert to this channel is written."}
              </p>
            </div>
          ) : null}

          {loading ? (
            <Skeleton className="h-20" />
          ) : channels.length ? (
            <ul className="divide-y divide-line">
              {channels.map((channel) => (
                <li key={String(channel.id)} className="flex items-center gap-3 py-2.5">
                  <Badge tone="outline">{String(channel.kind)}</Badge>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                    {String(channel.name)}
                  </span>
                  <span className="mono min-w-0 max-w-64 truncate text-[11.5px] text-ink-subtle">
                    {String(channel.target)}
                  </span>
                  {canWrite ? (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={"Remove " + String(channel.name)}
                      onClick={() => remove(String(channel.id))}
                    >
                      <Trash2 />
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Bell}
              title="No channels configured"
              description={
                canWrite
                  ? "Add an email address or a webhook URL above to be told about budgets, failed runs and quota changes."
                  : "Nobody is being told about budgets, failed runs or quota changes yet."
              }
            />
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}

export { Section };
