/**
 * Custom roles.
 *
 * The five built-in roles cover most shapes; this is where an owner defines
 * the ones they do not. Permissions are grouped and described in words,
 * because a checkbox labelled `payload:read` tells nobody what they are about
 * to grant.
 *
 * Writing roles is owner-only. Everyone with `role:read` sees the list, since
 * that is who assigns them.
 */

import { Check, Lock, Pencil, Plus, Shield, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  Input,
  Field,
  Skeleton,
} from "@/components/ui";
import { EmptyState } from "@/components/shared";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PERMISSIONS, useSession } from "@/stores/session";
import type { CustomRole, RoleCatalogue } from "@/types/api";

type Draft = {
  id?: string;
  name: string;
  description: string;
  permissions: Set<string>;
};

const EMPTY: Draft = { name: "", description: "", permissions: new Set() };

export function RolesSettings() {
  const { can } = useSession();
  const canWrite = can(PERMISSIONS.roleWrite);

  const [roles, setRoles] = React.useState<CustomRole[]>([]);
  const [catalogue, setCatalogue] = React.useState<RoleCatalogue | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [draft, setDraft] = React.useState<Draft | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState<CustomRole | null>(null);

  const refresh = React.useCallback(async () => {
    const [listed, cat] = await Promise.all([
      api.roles().catch(() => ({ items: [], total: 0 })),
      api.rolePermissions().catch(() => null),
    ]);
    setRoles(listed.items ?? []);
    setCatalogue(cat);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const grouped = React.useMemo(() => {
    if (!catalogue) return [];
    return catalogue.groups.map((group) => ({
      group,
      permissions: catalogue.permissions.filter((p) => p.group === group),
    }));
  }, [catalogue]);

  async function save() {
    if (!draft) return;
    const permissions = [...draft.permissions];
    if (!draft.name.trim()) {
      toast.error("Give the role a name.");
      return;
    }
    if (!permissions.length) {
      toast.error("Choose at least one permission.");
      return;
    }

    setSaving(true);
    try {
      if (draft.id) {
        await api.updateRole(draft.id, {
          name: draft.name,
          description: draft.description,
          permissions,
        });
        toast.success("Role updated.");
      } else {
        await api.createRole({
          name: draft.name,
          description: draft.description,
          permissions,
        });
        toast.success("Role created.");
      }
      setDraft(null);
      await refresh();
    } catch (error) {
      toast.error((error as { message?: string })?.message ?? "Could not save the role.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(role: CustomRole) {
    try {
      await api.deleteRole(role.id);
      toast.success("Role deleted.");
      setConfirmDelete(null);
      await refresh();
    } catch (error) {
      toast.error((error as { message?: string })?.message ?? "Could not delete the role.");
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Roles"
          icon={Shield}
          description="A role is a name and a set of permissions. Assign one to a member or an API key under Members and API keys."
          action={
            canWrite ? (
              <Button size="sm" onClick={() => setDraft({ ...EMPTY, permissions: new Set() })}>
                <Plus />
                New role
              </Button>
            ) : null
          }
        />
        <CardBody>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          ) : roles.length ? (
            <ul className="divide-y divide-line">
              {roles.map((role) => (
                <li key={role.id} className="flex items-start gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium text-ink">{role.name}</span>
                      <Badge tone="outline" className="mono">
                        {role.slug}
                      </Badge>
                      <span className="text-[11.5px] text-ink-subtle">
                        {role.permissions.length}{" "}
                        {role.permissions.length === 1 ? "permission" : "permissions"}
                        {role.assigned_count
                          ? " · assigned to " + role.assigned_count
                          : " · unassigned"}
                      </span>
                    </div>
                    {role.description ? (
                      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-muted">
                        {role.description}
                      </p>
                    ) : null}
                  </div>
                  {canWrite ? (
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={"Edit " + role.name}
                        onClick={() =>
                          setDraft({
                            id: role.id,
                            name: role.name,
                            description: role.description,
                            permissions: new Set(role.permissions),
                          })
                        }
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={"Delete " + role.name}
                        onClick={() => setConfirmDelete(role)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Shield}
              title="No custom roles"
              description="The built-in roles below cover most teams. Define a custom one when you need a permission set they do not offer."
              action={
                canWrite ? (
                  <Button size="sm" onClick={() => setDraft({ ...EMPTY, permissions: new Set() })}>
                    <Plus />
                    New role
                  </Button>
                ) : null
              }
            />
          )}
        </CardBody>
      </Card>

      {/* The built-ins, so an owner can see what exists before inventing
          something close to it. */}
      {catalogue ? (
        <Card>
          <CardHeader
            title="Built-in roles"
            icon={Lock}
            description="These cannot be changed or deleted."
          />
          <CardBody>
            <ul className="divide-y divide-line">
              {catalogue.builtin.map((role) => (
                <li key={role.slug} className="flex items-center gap-3 py-2.5">
                  <Badge tone="outline" className="mono">
                    {role.slug}
                  </Badge>
                  <span className="flex-1 text-[12.5px] text-ink-muted">
                    {role.permissions.length} permissions
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {/* ----------------------------------------------------------- editor */}
      <Dialog open={draft !== null} onOpenChange={(open) => !open && setDraft(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader
            title={draft?.id ? "Edit role" : "New role"}
            description={
              draft?.id
                ? "Changing the permissions takes effect the next time someone holding this role makes a request."
                : "Name the role and choose what it can do."
            }
          />

          {draft ? (
            <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Name">
                  <Input
                    value={draft.name}
                    onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                    placeholder="Cost auditor"
                  />
                </Field>
                <Field label="Description" hint="Optional">
                  <Input
                    value={draft.description}
                    onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                    placeholder="Reads spend and the audit log"
                  />
                </Field>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[12px] text-ink-subtle">
                  {draft.permissions.size} selected
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDraft({ ...draft, permissions: new Set() })}
                >
                  <X />
                  Clear all
                </Button>
              </div>

              <div className="space-y-3">
                {grouped.map(({ group, permissions }) => (
                  <div key={group} className="rounded-[var(--radius-sm)] border border-line">
                    <div className="flex items-center justify-between border-b border-line bg-surface-sunken px-3 py-2">
                      <span className="mono text-[11px] uppercase tracking-[0.1em] text-ink-subtle">
                        {group}
                      </span>
                      <button
                        type="button"
                        className="text-[11.5px] text-accent transition-colors hover:text-accent-strong"
                        onClick={() => {
                          const next = new Set(draft.permissions);
                          const all = permissions.every((p) => next.has(p.value));
                          permissions.forEach((p) =>
                            all ? next.delete(p.value) : next.add(p.value),
                          );
                          setDraft({ ...draft, permissions: next });
                        }}
                      >
                        {permissions.every((p) => draft.permissions.has(p.value))
                          ? "None"
                          : "All"}
                      </button>
                    </div>
                    <ul className="divide-y divide-line">
                      {permissions.map((permission) => {
                        const checked = draft.permissions.has(permission.value);
                        return (
                          <li key={permission.value}>
                            <label
                              className={cn(
                                "flex cursor-pointer items-start gap-2.5 px-3 py-2 transition-colors",
                                checked ? "bg-accent-ghost/35" : "hover:bg-surface-sunken",
                              )}
                            >
                              <Checkbox
                                checked={checked}
                                onCheckedChange={() => {
                                  const next = new Set(draft.permissions);
                                  if (checked) next.delete(permission.value);
                                  else next.add(permission.value);
                                  setDraft({ ...draft, permissions: next });
                                }}
                                className="mt-0.5"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block text-[12.5px] leading-snug text-ink">
                                  {permission.label}
                                </span>
                                <span className="mono block text-[10.5px] text-ink-subtle">
                                  {permission.value}
                                </span>
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="ghost" onClick={() => setDraft(null)}>
              Cancel
            </Button>
            <Button onClick={save} disabled={saving}>
              <Check />
              {draft?.id ? "Save changes" : "Create role"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ----------------------------------------------------------- delete */}
      <Dialog open={confirmDelete !== null} onOpenChange={(open) => !open && setConfirmDelete(null)}>
        <DialogContent>
          <DialogHeader
            title={"Delete " + (confirmDelete?.name ?? "role") + "?"}
            description={
              confirmDelete?.assigned_count
                ? "This role is assigned to " +
                  confirmDelete.assigned_count +
                  " member or key. Move them to another role first - deleting it would leave them with no permissions at all."
                : "Nothing holds this role, so deleting it changes nobody's access."
            }
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={Boolean(confirmDelete?.assigned_count)}
              onClick={() => confirmDelete && remove(confirmDelete)}
            >
              <Trash2 />
              Delete role
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
