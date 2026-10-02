/** Session state: who is signed in, which organization and project are active. */

import { create } from "zustand";

import { activeProject, api, tokens } from "@/lib/api";
import type { Me, Project } from "@/types/api";

interface SessionState {
  me: Me | null;
  project: Project | null;
  status: "idle" | "loading" | "authenticated" | "anonymous";
  error: string | null;

  load: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (body: {
    email: string;
    password: string;
    full_name?: string;
    organization_name?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  selectProject: (id: string) => void;
  can: (permission: string) => boolean;
}

function resolveProject(me: Me): Project | null {
  const stored = activeProject.get();
  const match = me.projects.find((project) => project.id === stored);
  const chosen = match ?? me.projects[0] ?? null;
  activeProject.set(chosen?.id ?? null);
  return chosen;
}

export const useSession = create<SessionState>((set, get) => ({
  me: null,
  project: null,
  status: "idle",
  error: null,

  async load() {
    if (!tokens.access() && !tokens.refresh()) {
      set({ status: "anonymous", me: null, project: null });
      return;
    }
    set({ status: "loading", error: null });
    try {
      const me = await api.me();
      set({ me, project: resolveProject(me), status: "authenticated" });
    } catch {
      tokens.clear();
      set({ status: "anonymous", me: null, project: null });
    }
  },

  async login(email, password) {
    set({ error: null });
    const response = await api.login({ email, password });
    tokens.set(response);
    const me = await api.me();
    set({ me, project: resolveProject(me), status: "authenticated" });
  },

  async register(body) {
    set({ error: null });
    const response = await api.register(body);
    tokens.set(response);
    const me = await api.me();
    set({ me, project: resolveProject(me), status: "authenticated" });
  },

  async logout() {
    try {
      await api.logout();
    } catch {
      /* the local session is cleared either way */
    }
    tokens.clear();
    activeProject.set(null);
    set({ me: null, project: null, status: "anonymous" });
  },

  selectProject(id) {
    const me = get().me;
    const project = me?.projects.find((candidate) => candidate.id === id) ?? null;
    activeProject.set(project?.id ?? null);
    set({ project });
  },

  /**
   * Section 34: the server is the authority on permissions. This mirrors the
   * resolved set so the UI can hide what the caller cannot do, rather than
   * offering an action that will 403.
   */
  can(permission) {
    return get().me?.permissions.includes(permission) ?? false;
  },
}));

export const PERMISSIONS = {
  plan: "plan:create",
  execute: "run:execute",
  runRead: "run:read",
  runReplay: "run:replay",
  payloadRead: "payload:read",
  cacheRead: "cache:read",
  cacheInvalidate: "cache:invalidate",
  budgetRead: "budget:read",
  budgetWrite: "budget:write",
  analyticsRead: "analytics:read",
  benchmarkRead: "benchmark:read",
  benchmarkRun: "benchmark:run",
  auditRead: "audit:read",
  auditExport: "audit:export",
  memberRead: "member:read",
  memberWrite: "member:write",
  projectWrite: "project:write",
  keyRead: "key:read",
  keyWrite: "key:write",
  keyProjectWrite: "key:project_write",
  credentialRead: "credential:read",
  credentialWrite: "credential:write",
  credentialRotate: "credential:rotate",
  catalogRead: "catalog:read",
  alertRead: "alert:read",
  alertWrite: "alert:write",
  orgUpdate: "org:update",
  policyWrite: "policy:write",
} as const;
