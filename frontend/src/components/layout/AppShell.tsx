import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Building2,
  ChevronsUpDown,
  Database,
  FileText,
  Gauge,
  GitBranch,
  Key,
  LogOut,
  Network,
  Route,
  Search,
  Settings,
  Shield,
  Terminal,
  Users,
  Wallet,
} from "lucide-react";
import * as React from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { pageVariants } from "@/animations";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { ModeBadge } from "@/components/shared";
import { useCardReveal, useFigureCounters } from "@/hooks/useConsoleMotion";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui";
import { useHealth } from "@/hooks/useQueries";
import { cn } from "@/lib/utils";
import { PERMISSIONS, useSession } from "@/stores/session";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  permission?: string;
  end?: boolean;
}

const NAVIGATION: { group: string; items: NavItem[] }[] = [
  {
    group: "Operate",
    items: [
      { to: "/app", label: "Overview", icon: Gauge, end: true },
      { to: "/app/search", label: "Search", icon: Search, permission: PERMISSIONS.plan },
      { to: "/app/runs", label: "Runs", icon: Activity, permission: PERMISSIONS.runRead },
      { to: "/app/plans", label: "Plan Inspector", icon: Route, permission: PERMISSIONS.runRead },
    ],
  },
  {
    group: "Infrastructure",
    items: [
      { to: "/app/catalog", label: "Catalog", icon: Network, permission: PERMISSIONS.catalogRead },
      { to: "/app/cache", label: "Cache", icon: Database, permission: PERMISSIONS.cacheRead },
      { to: "/app/budgets", label: "Budgets", icon: Wallet, permission: PERMISSIONS.budgetRead },
    ],
  },
  {
    group: "Evidence",
    items: [
      {
        to: "/app/analytics",
        label: "Analytics",
        icon: BarChart3,
        permission: PERMISSIONS.analyticsRead,
      },
      {
        to: "/app/benchmarks",
        label: "Benchmarks",
        icon: GitBranch,
        permission: PERMISSIONS.benchmarkRead,
      },
      { to: "/app/audit", label: "Audit Log", icon: Shield, permission: PERMISSIONS.auditRead },
    ],
  },
];

/**
 * The console's footer.
 *
 * Deliberately quiet: the version, the catalog it is running, and the few
 * links somebody actually leaves the console for. It also gives every page a
 * defined end, which a scroll container otherwise lacks.
 */
function ConsoleFooter() {
  const health = useHealth();
  const year = new Date().getFullYear();

  return (
    <footer className="mt-10 border-t border-line pt-5 pb-1">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-ink-subtle">
          <span>&copy; {year} SerpFlow. All rights reserved.</span>
          <span className="mono">Apache-2.0</span>
          {health.data?.catalog_version ? (
            <span className="mono">catalog {health.data.catalog_version}</span>
          ) : null}
          {health.data?.mode ? (
            <ModeBadge mode={health.data.mode} className="scale-90" />
          ) : null}
        </div>

        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px]">
          <Link to="/" className="text-ink-subtle transition-colors hover:text-ink">
            Home
          </Link>
          <Link to="/docs" className="text-ink-subtle transition-colors hover:text-ink">
            Documentation
          </Link>
          <Link to="/api" className="text-ink-subtle transition-colors hover:text-ink">
            API reference
          </Link>
          <Link
            to="/app/settings/organization"
            className="text-ink-subtle transition-colors hover:text-ink"
          >
            Settings
          </Link>
          <a
            href="https://github.com/serpflow/serpflow"
            target="_blank"
            rel="noreferrer noopener"
            className="text-ink-subtle transition-colors hover:text-ink"
          >
            Source
          </a>
        </nav>
      </div>
    </footer>
  );
}

export function AppShell() {
  const { me, project, selectProject, logout, can } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const health = useHealth();

  // Cards rise into place as they cross the fold, and figures count up. Keyed
  // on the path so a navigation re-runs it against the page that just
  // mounted; `motion.main` is re-keyed on the same value, so the ref is fresh.
  const motionRef = React.useRef<HTMLElement>(null);
  useCardReveal(motionRef, { stagger: 0.04 });
  useFigureCounters(motionRef);

  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);


  return (
    <div className="flex h-dvh overflow-hidden bg-ground">
      {/* ----------------------------------------------------- sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface-sunken lg:flex">
        <Link
          to="/"
          aria-label="SerpFlow home"
          className="group flex h-14 items-center gap-2.5 border-b border-line px-4 transition-colors duration-300 hover:bg-surface"
        >
          <Mark />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold leading-none text-ink">SerpFlow</p>
            <p className="mono mt-1 truncate text-[10px] leading-none text-ink-subtle transition-colors duration-300 group-hover:text-ink-muted">
              {health.data?.catalog_version ?? "catalog loading"}
            </p>
          </div>
        </Link>

        <nav className="scrollbar-none flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {NAVIGATION.map((section) => {
            const items = section.items.filter(
              (item) => !item.permission || can(item.permission),
            );
            if (!items.length) return null;
            return (
              <div key={section.group}>
                <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-[0.1em] text-ink-subtle">
                  {section.group}
                </p>
                <div className="space-y-0.5">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) =>
                        cn(
                          "group relative flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2 py-1.5 text-[13px] transition-colors",
                          isActive
                            ? "bg-surface-raised text-ink"
                            : "text-ink-muted hover:bg-surface hover:text-ink",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive ? (
                            <motion.span
                              layoutId="nav-active"
                              className="absolute inset-y-1 -left-3 w-0.5 rounded-r bg-accent"
                              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                            />
                          ) : null}
                          <item.icon className="size-4 shrink-0" />
                          {item.label}
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}

          <div>
            <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-[0.1em] text-ink-subtle">
              Configure
            </p>
            <NavLink
              to="/app/settings"
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-[var(--radius-sm)] px-2 py-1.5 text-[13px] transition-colors",
                  isActive
                    ? "bg-surface-raised text-ink"
                    : "text-ink-muted hover:bg-surface hover:text-ink",
                )
              }
            >
              <Settings className="size-4" />
              Settings
            </NavLink>
          </div>
        </nav>

        {/* Section 73: organization, project, environment and principal. */}
        <div className="border-t border-line p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex w-full items-center gap-2.5 rounded-[var(--radius-sm)] border border-line bg-surface px-2.5 py-2 text-left transition-colors hover:border-line-strong">
                <Building2 className="size-4 shrink-0 text-ink-subtle" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium leading-none text-ink">
                    {me?.organization?.name ?? "Organization"}
                  </p>
                  <p className="mt-1 truncate text-[11px] leading-none text-ink-subtle">
                    {project?.name ?? "No project"}
                  </p>
                </div>
                <ChevronsUpDown className="size-3.5 shrink-0 text-ink-subtle" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56">
              <DropdownMenuLabel>Project</DropdownMenuLabel>
              {me?.projects.map((candidate) => (
                <DropdownMenuItem
                  key={candidate.id}
                  onSelect={() => selectProject(candidate.id)}
                  className={candidate.id === project?.id ? "bg-surface-raised" : ""}
                >
                  <Terminal />
                  <span className="flex-1 truncate">{candidate.name}</span>
                  <span className="mono text-[10px] text-ink-subtle">
                    {candidate.key_prefix}
                  </span>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => navigate("/app/settings/projects")}>
                <Settings />
                Manage projects
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>


        </div>
      </aside>

      {/* ------------------------------------------------------- main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface-sunken px-4 lg:px-6">
          <button
            onClick={() => setPaletteOpen(true)}
            className="group flex h-8 min-w-0 flex-1 items-center gap-2.5 rounded-[var(--radius-sm)] border border-line bg-surface px-3 text-left transition-colors hover:border-line-strong sm:max-w-sm"
          >
            <Search className="size-3.5 shrink-0 text-ink-subtle" />
            <span className="flex-1 truncate text-[12px] text-ink-subtle">
              Search, jump to a run, inspect an engine
            </span>
            <kbd className="mono hidden rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-subtle sm:inline">
              Ctrl K
            </kbd>
          </button>

          <div className="flex items-center gap-2">
            {project ? (
              <Badge tone="outline" className="mono hidden sm:inline-flex">
                {project.key_prefix}
              </Badge>
            ) : null}

            <ThemeToggle className="h-8 w-8" />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2">
                  <span className="flex size-5 items-center justify-center rounded-full border border-line bg-surface text-[10px] font-semibold text-ink-muted">
                    {(me?.user?.full_name ?? me?.user?.email ?? "S").slice(0, 1).toUpperCase()}
                  </span>
                  <span className="hidden max-w-32 truncate sm:inline">
                    {me?.user?.full_name || me?.user?.email || me?.principal_type}
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-60">
                <div className="px-2 py-2">
                  <p className="truncate text-[13px] font-medium text-ink">
                    {me?.user?.full_name || me?.user?.email}
                  </p>
                  <p className="mt-0.5 text-[11px] text-ink-subtle">
                    {me?.role} in {me?.organization?.name}
                  </p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => navigate("/app/settings/organization")}>
                  <Building2 />
                  Organization
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => navigate("/app/settings/members")}>
                  <Users />
                  Members
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => navigate("/app/settings/api-keys")}>
                  <Key />
                  API keys
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => navigate("/app/settings/credentials")}>
                  <Shield />
                  Credentials
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => window.open("/docs", "_blank", "noopener")}
                >
                  <FileText />
                  API reference
                </DropdownMenuItem>
                <DropdownMenuItem
                  danger
                  onSelect={async () => {
                    await logout();
                    navigate("/login");
                  }}
                >
                  <LogOut />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Native scrolling, deliberately: see useSmoothScroll. Lenis here
            cached the first page's height, so a taller page stopped short. */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <AnimatePresence
            mode="wait"
            onExitComplete={() => scrollRef.current?.scrollTo({ top: 0 })}
          >
            <motion.main
              key={location.pathname}
              ref={motionRef}
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className="mx-auto w-full max-w-[1500px] px-4 py-6 lg:px-8 lg:py-8"
            >
              <Outlet />
            
              <ConsoleFooter />
            </motion.main>
          </AnimatePresence>
        </div>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}

/** A small routed-graph mark: three nodes, two typed edges. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("size-6 shrink-0", className)}
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 6h4.5a3 3 0 0 1 3 3v6a3 3 0 0 0 3 3H19"
        stroke="var(--color-accent)"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="4" cy="6" r="2.1" fill="var(--color-accent)" />
      <circle cx="20" cy="18" r="2.1" fill="var(--color-warm)" />
      <circle
        cx="12.5"
        cy="12"
        r="1.7"
        fill="var(--color-ground)"
        stroke="var(--color-accent)"
        strokeWidth="1.4"
      />
    </svg>
  );
}
