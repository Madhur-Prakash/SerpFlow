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
  Key,
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
  useCredentials,
  useMembers,
  useProjects,
  useSessions,
} from "@/hooks/useQueries";
import { api } from "@/lib/api";
import * as fmt from "@/lib/format";
import { cn } from "@/lib/utils";
import { PERMISSIONS, useSession } from "@/stores/session";

const TABS = [
  { to: "organization", label: "Organization", icon: Building2 },
  { to: "members", label: "Members", icon: Users },
  { to: "projects", label: "Projects", icon: Terminal },
  { to: "api-keys", label: "API keys", icon: Key },
  { to: "credentials", label: "Credentials", icon: Shield },
  { to: "security", label: "Security", icon: Lock },
  { to: "notifications", label: "Notifications", icon: Bell },
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
        <Route path="projects" element={<ProjectsSettings />} />
        <Route path="api-keys" element={<ApiKeysSettings />} />
        <Route path="credentials" element={<CredentialsSettings />} />
        <Route path="security" element={<SecuritySettings />} />
        <Route path="notifications" element={<NotificationsSettings />} />
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
function MembersSettings() {
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
  const { can } = useSession();
  const [open, setOpen] = React.useState(false);
  const canWrite = can(PERMISSIONS.credentialWrite);
  const canRotate = can(PERMISSIONS.credentialRotate);

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate" className="space-y-4">
      <Card>
        <CardHeader
          title="Upstream SerpApi credentials"
          icon={Shield}
          description="Resolution order: the project's own credential, then the organization default, then refuse."
          action={
            canWrite ? (
              <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
                <Plus />
                Add credential
              </Button>
            ) : null
          }
        />
        <CardBody className="space-y-3">
          <Alert tone="accent" icon={Lock} title="The key is encrypted and never returned">
            Each credential gets a random data key, itself encrypted under a key-encryption
            key. Only the fingerprint - sha256 of the key, first eight characters - is ever
            shown, and no API response schema has a field that could carry the secret.
          </Alert>

          {credentials.isLoading ? (
            <Skeleton className="h-24" />
          ) : credentials.data?.length ? (
            <ul className="divide-y divide-line">
              {credentials.data.map((credential) => (
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
                        ? " - " + credential.upstream_searches_left + " searches left upstream"
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
                            toast.success("Credential validated");
                            credentials.refetch();
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
          ) : (
            <EmptyState
              icon={Shield}
              title="No credential attached"
              description="Without one, live API keys cannot execute and SerpFlow returns NO_UPSTREAM_CREDENTIAL rather than failing mid-run. Test keys do not need one: they route to the deterministic mock."
              action={
                canWrite ? (
                  <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
                    <Plus />
                    Add credential
                  </Button>
                ) : null
              }
            />
          )}
        </CardBody>
      </Card>

      <AddCredentialDialog
        open={open}
        onOpenChange={setOpen}
        onCreated={() => credentials.refetch()}
      />
    </motion.div>
  );
}

function AddCredentialDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const [name, setName] = React.useState("Primary SerpApi account");
  const [apiKey, setApiKey] = React.useState("");
  const [validateNow, setValidateNow] = React.useState(true);
  const [saving, setSaving] = React.useState(false);

  async function submit() {
    setSaving(true);
    try {
      await api.createCredential({
        name,
        api_key: apiKey,
        validate_now: validateNow,
        set_as_org_default: true,
      });
      toast.success("Credential stored", {
        description: "Only its fingerprint is retrievable from now on.",
      });
      setApiKey("");
      onOpenChange(false);
      onCreated();
    } catch (error) {
      toast.error("Could not store the credential", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title="Add a SerpApi credential"
          description="This is the key SerpFlow spends on your behalf. It is separate from the API keys your code uses to call SerpFlow."
        />
        <div className="space-y-4 px-5 py-4">
          <Field label="Name">
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field
            label="SerpApi key"
            hint="Encrypted immediately. After this dialog closes there is no way to read it back."
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="64 hex characters"
              className="mono"
              autoComplete="off"
            />
          </Field>
          <div className="flex items-center justify-between gap-4 rounded-[var(--radius-sm)] border border-line bg-surface-sunken px-3 py-2.5">
            <div>
              <p className="text-[13px] font-medium text-ink">Validate now</p>
              <p className="mt-0.5 text-[12px] text-ink-subtle text-pretty">
                One cheap account call to prove the key works, before you depend on it.
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
function NotificationsSettings() {
  const [channels, setChannels] = React.useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api
      .channels()
      .then(setChannels)
      .catch(() => setChannels([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <motion.div variants={listVariants} initial="initial" animate="animate">
      <Card>
        <CardHeader
          title="Notification channels"
          icon={Bell}
          description="Webhook deliveries are signed and retried through Kafka. Events: budget thresholds, run completion and failure, anomalous spend, routing regressions, credential validation failures and upstream quota changes."
        />
        <CardBody>
          {loading ? (
            <Skeleton className="h-20" />
          ) : channels.length ? (
            <ul className="divide-y divide-line">
              {channels.map((channel, index) => (
                <li key={index} className="flex items-center gap-3 py-2.5">
                  <Badge tone="outline">{String(channel.kind)}</Badge>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-ink">
                    {String(channel.name)}
                  </span>
                  <span className="mono truncate text-[11px] text-ink-subtle">
                    {String(channel.target)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Bell}
              title="No channels configured"
              description="A channel receives signed webhook deliveries when a budget crosses its threshold, a run fails, routing accuracy regresses, or the upstream quota diverges from the internal ledger."
            />
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}

export { Section };
