/**
 * The catalog as an interactive graph (section 49).
 *
 * Two edge kinds, drawn so they can never be confused:
 *
 *   dependency  solid, arrowed      how engines CHAIN
 *   substitute  dashed, no arrow    how engines COMPETE
 *
 * Engines are placed by a small force layout seeded from their capability
 * tags (forceLayout.ts), so the picture is the same on every load. A reader
 * can zoom towards the pointer, pan, drag engines apart, hover any engine or
 * edge for what it carries, and click an engine to pin its neighbourhood and
 * walk its chains from a details panel.
 */

import { ArrowRight, Maximize2, Minus, Plus, RotateCcw, Search, X } from "lucide-react";
import * as React from "react";

import { prefersReducedMotion } from "@/animations";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { CatalogGraph as CatalogGraphData } from "@/types/api";

import { ForceLayout, type SimNode } from "./forceLayout";

type GraphNode = CatalogGraphData["nodes"][number];

interface Props {
  data: CatalogGraphData;
  focus?: string | null;
  onSelect?: (engine: string) => void;
  /** Clicking empty space or closing the details panel. */
  onClear?: () => void;
  /** "Open in Explore" from the details panel. */
  onOpen?: (engine: string) => void;
  showSubstitutes?: boolean;
  className?: string;
}

interface View {
  x: number;
  y: number;
  k: number;
}

type Hover =
  | { kind: "node"; id: string }
  | { kind: "dependency"; index: number }
  | { kind: "substitute"; index: number }
  | null;

type Gesture =
  | { kind: "pan"; start: Point; origin: View; moved: boolean }
  | { kind: "drag"; id: string; start: Point; moved: boolean }
  | null;

interface Point {
  x: number;
  y: number;
}

const MIN_ZOOM = 0.3;
const MAX_ZOOM = 3;
// Below this zoom only hubs and the active neighbourhood keep their labels.
const LABEL_ZOOM = 0.95;
const PANEL_WIDTH = 300;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const radiusOf = (node: GraphNode) => 5 + Math.min(node.in_degree + node.out_degree, 6) * 1.25;

/**
 * Seed every primary capability tag at its own point on an ellipse with its
 * members around it, so substitutes start together, then settle the forces.
 */
function buildLayout(data: CatalogGraphData) {
  const byTag = new Map<string, GraphNode[]>();
  for (const node of data.nodes) {
    const tag = node.tags[0] ?? "other";
    byTag.set(tag, [...(byTag.get(tag) ?? []), node]);
  }
  const tags = [...byTag.keys()].sort(
    (a, b) => (byTag.get(b)?.length ?? 0) - (byTag.get(a)?.length ?? 0) || a.localeCompare(b),
  );

  const nodes: SimNode[] = [];
  tags.forEach((tag, tagIndex) => {
    const members = (byTag.get(tag) ?? []).slice().sort((a, b) => a.id.localeCompare(b.id));
    const angle = (tagIndex / tags.length) * Math.PI * 2;
    const groupX = Math.cos(angle) * 280;
    const groupY = Math.sin(angle) * 180;
    members.forEach((node, memberIndex) => {
      const local = angle + (memberIndex / members.length) * Math.PI * 2;
      const spread = members.length === 1 ? 0 : 32;
      const radius = radiusOf(node);
      nodes.push({
        id: node.id,
        x: groupX + Math.cos(local) * spread,
        y: groupY + Math.sin(local) * spread,
        vx: 0,
        vy: 0,
        fx: null,
        fy: null,
        radius,
        collide: radius + 18,
      });
    });
  });

  // Substitute springs are kept even when substitutes are hidden, so the
  // toggle never moves anything.
  const sim = new ForceLayout(nodes, [
    ...data.dependency_edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      distance: 95,
      strength: 0.5,
    })),
    ...data.substitute_edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      distance: 150,
      strength: 0.05,
    })),
  ]);
  sim.settle();
  const home = new Map(nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
  return { sim, home };
}

/** A curved dependency path that stops at the target's edge, plus its arrow tip. */
function dependencyGeometry(source: SimNode, target: SimNode) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const length = Math.hypot(dx, dy) || 1;
  const bend = Math.min(42, length * 0.18);
  const cx = (source.x + target.x) / 2 + (-dy / length) * bend;
  const cy = (source.y + target.y) / 2 + (dx / length) * bend;

  const sx = cx - source.x;
  const sy = cy - source.y;
  const sl = Math.hypot(sx, sy) || 1;
  const ex = target.x - cx;
  const ey = target.y - cy;
  const el = Math.hypot(ex, ey) || 1;
  const start = { x: source.x + (sx / sl) * (source.radius + 1), y: source.y + (sy / sl) * (source.radius + 1) };
  const end = { x: target.x - (ex / el) * (target.radius + 2), y: target.y - (ey / el) * (target.radius + 2) };
  return {
    d: `M${start.x} ${start.y} Q${cx} ${cy} ${end.x} ${end.y}`,
    tip: end,
    direction: { x: ex / el, y: ey / el },
  };
}

export function CatalogGraph({
  data,
  focus = null,
  onSelect,
  onClear,
  onOpen,
  showSubstitutes = true,
  className,
}: Props) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const svgRef = React.useRef<SVGSVGElement>(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });
  const [view, setView] = React.useState<View>({ x: 0, y: 0, k: 1 });
  const viewRef = React.useRef(view);
  const [hover, setHover] = React.useState<Hover>(null);
  const [pointer, setPointer] = React.useState<Point>({ x: 0, y: 0 });
  const [query, setQuery] = React.useState("");
  const [, setFrame] = React.useState(0);
  const gesture = React.useRef<Gesture>(null);
  const tween = React.useRef<number | null>(null);
  const run = React.useRef<number | null>(null);
  const framed = React.useRef(false);

  const { sim, home } = React.useMemo(() => buildLayout(data), [data]);
  const simById = React.useMemo(() => new Map(sim.nodes.map((node) => [node.id, node])), [sim]);
  const nodeById = React.useMemo(() => new Map(data.nodes.map((node) => [node.id, node])), [data]);

  React.useLayoutEffect(() => {
    viewRef.current = view;
  }, [view]);

  // ------------------------------------------------------------ neighbours
  const adjacency = React.useMemo(() => {
    const dependencies = new Map<string, Set<string>>();
    const substitutes = new Map<string, Set<string>>();
    const link = (map: Map<string, Set<string>>, a: string, b: string) => {
      map.set(a, (map.get(a) ?? new Set()).add(b));
      map.set(b, (map.get(b) ?? new Set()).add(a));
    };
    for (const edge of data.dependency_edges) link(dependencies, edge.source, edge.target);
    for (const edge of data.substitute_edges) link(substitutes, edge.source, edge.target);
    return { dependencies, substitutes };
  }, [data]);

  const hoveredNode = hover?.kind === "node" ? hover.id : null;
  const active = hoveredNode ?? focus;
  const neighbourhood = React.useMemo(() => {
    if (!active) return null;
    const set = new Set<string>([active, ...(adjacency.dependencies.get(active) ?? [])]);
    if (showSubstitutes) for (const id of adjacency.substitutes.get(active) ?? []) set.add(id);
    return set;
  }, [active, adjacency, showSubstitutes]);

  // ---------------------------------------------------------------- camera
  React.useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const stopTween = React.useCallback(() => {
    if (tween.current != null) cancelAnimationFrame(tween.current);
    tween.current = null;
  }, []);

  const animateTo = React.useCallback(
    (target: View) => {
      stopTween();
      if (prefersReducedMotion()) {
        setView(target);
        return;
      }
      const from = viewRef.current;
      const started = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - started) / 480);
        const e = 1 - Math.pow(1 - t, 3);
        setView({
          x: from.x + (target.x - from.x) * e,
          y: from.y + (target.y - from.y) * e,
          k: from.k + (target.k - from.k) * e,
        });
        tween.current = t < 1 ? requestAnimationFrame(step) : null;
      };
      tween.current = requestAnimationFrame(step);
    },
    [stopTween],
  );

  /** The view that frames `ids` (or everything), clear of the details panel. */
  const frameFor = React.useCallback(
    (ids: string[] | null, panelOpen: boolean, maxZoom: number): View | null => {
      if (!size.width || !size.height) return null;
      const points = ids
        ? ids.flatMap((id) => (simById.has(id) ? [simById.get(id)!] : []))
        : sim.nodes;
      if (!points.length) return null;
      let x0 = Infinity;
      let y0 = Infinity;
      let x1 = -Infinity;
      let y1 = -Infinity;
      for (const point of points) {
        x0 = Math.min(x0, point.x - point.collide);
        y0 = Math.min(y0, point.y - point.collide);
        x1 = Math.max(x1, point.x + point.collide);
        y1 = Math.max(y1, point.y + point.collide);
      }
      const reserve = panelOpen && size.width > 760 ? PANEL_WIDTH + 24 : 0;
      const width = size.width - reserve;
      // Labels hang below nodes and run wide (up to ~30 mono characters),
      // so the horizontal margin is generous enough to keep them on screen.
      const padX = 150;
      const padY = 64;
      const k = clamp(
        Math.min(
          Math.max(width - padX * 2, 120) / (x1 - x0 || 1),
          Math.max(size.height - padY * 2, 120) / (y1 - y0 || 1),
        ),
        MIN_ZOOM,
        maxZoom,
      );
      return { k, x: width / 2 - ((x0 + x1) / 2) * k, y: size.height / 2 - ((y0 + y1) / 2) * k };
    },
    [size, sim, simById],
  );

  // Frame the whole catalog, or the focused engine with everything it
  // touches. Runs on first size, when the focus changes and on resize.
  React.useEffect(() => {
    const ids = focus
      ? [focus, ...(adjacency.dependencies.get(focus) ?? []), ...(adjacency.substitutes.get(focus) ?? [])]
      : null;
    const target = frameFor(ids, Boolean(focus), focus ? 1.5 : 1.1);
    if (!target) return;
    if (!framed.current) {
      framed.current = true;
      setView(target);
    } else {
      animateTo(target);
    }
  }, [focus, adjacency, frameFor, animateTo]);

  const zoomBy = (factor: number) => {
    const v = viewRef.current;
    const k = clamp(v.k * factor, MIN_ZOOM, MAX_ZOOM);
    const cx = size.width / 2;
    const cy = size.height / 2;
    animateTo({ k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k });
  };

  const fitAll = () => {
    const target = frameFor(null, Boolean(focus), 1.1);
    if (target) animateTo(target);
  };

  // Wheel zooms towards the pointer. Registered natively: React's wheel
  // listener is passive, and the page must not scroll underneath.
  React.useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      stopTween();
      const rect = svg.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const v = viewRef.current;
      const step = event.deltaMode === 1 ? event.deltaY * 0.05 : event.deltaY * 0.0015;
      const k = clamp(v.k * Math.exp(-step), MIN_ZOOM, MAX_ZOOM);
      setView({ k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [stopTween]);

  // -------------------------------------------------------------- physics
  const kick = React.useCallback(() => {
    if (run.current != null) return;
    const step = () => {
      sim.tick();
      setFrame((frame) => frame + 1);
      run.current = sim.active ? requestAnimationFrame(step) : null;
    };
    run.current = requestAnimationFrame(step);
  }, [sim]);

  React.useEffect(
    () => () => {
      if (run.current != null) cancelAnimationFrame(run.current);
      if (tween.current != null) cancelAnimationFrame(tween.current);
    },
    [],
  );

  const resetLayout = () => {
    for (const node of sim.nodes) {
      const start = home.get(node.id);
      if (!start) continue;
      node.x = start.x;
      node.y = start.y;
      node.vx = 0;
      node.vy = 0;
      node.fx = null;
      node.fy = null;
    }
    sim.alpha = 0;
    setFrame((frame) => frame + 1);
    fitAll();
  };

  // ------------------------------------------------------------- pointer
  const local = (event: { clientX: number; clientY: number }): Point => {
    const rect = svgRef.current?.getBoundingClientRect();
    return { x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) };
  };

  const onBackgroundDown = (event: React.PointerEvent) => {
    if (event.button !== 0) return;
    stopTween();
    svgRef.current?.setPointerCapture(event.pointerId);
    gesture.current = { kind: "pan", start: local(event), origin: viewRef.current, moved: false };
  };

  const onNodeDown = (event: React.PointerEvent, id: string) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    stopTween();
    svgRef.current?.setPointerCapture(event.pointerId);
    gesture.current = { kind: "drag", id, start: local(event), moved: false };
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const point = local(event);
    setPointer(point);
    const current = gesture.current;
    if (!current) return;
    if (!current.moved && Math.hypot(point.x - current.start.x, point.y - current.start.y) < 4) return;
    current.moved = true;
    if (current.kind === "pan") {
      setView({
        k: current.origin.k,
        x: current.origin.x + point.x - current.start.x,
        y: current.origin.y + point.y - current.start.y,
      });
      return;
    }
    const node = simById.get(current.id);
    if (!node) return;
    const v = viewRef.current;
    node.fx = (point.x - v.x) / v.k;
    node.fy = (point.y - v.y) / v.k;
    sim.alphaTarget = 0.3;
    kick();
  };

  const onPointerUp = (event: React.PointerEvent) => {
    const current = gesture.current;
    gesture.current = null;
    if (svgRef.current?.hasPointerCapture(event.pointerId)) {
      svgRef.current.releasePointerCapture(event.pointerId);
    }
    if (!current) return;
    if (current.kind === "drag") {
      // A dropped engine stays where it was put until the layout is reset.
      sim.alphaTarget = 0;
      if (current.moved) kick();
      else onSelect?.(current.id);
    } else if (!current.moved) {
      onClear?.();
    }
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if ((event.target as HTMLElement).tagName === "INPUT") return;
    const pan = (dx: number, dy: number) => {
      const v = viewRef.current;
      animateTo({ ...v, x: v.x + dx, y: v.y + dy });
    };
    const actions: Record<string, () => void> = {
      "+": () => zoomBy(1.3),
      "=": () => zoomBy(1.3),
      "-": () => zoomBy(1 / 1.3),
      "0": fitAll,
      Escape: () => onClear?.(),
      ArrowLeft: () => pan(80, 0),
      ArrowRight: () => pan(-80, 0),
      ArrowUp: () => pan(0, 80),
      ArrowDown: () => pan(0, -80),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };

  // -------------------------------------------------------------- search
  const needle = query.trim().toLowerCase();
  const matches = needle
    ? data.nodes
        .filter((node) => node.id.includes(needle) || node.tags.some((tag) => tag.includes(needle)))
        .slice(0, 6)
    : [];
  const choose = (id: string) => {
    setQuery("");
    onSelect?.(id);
  };

  // -------------------------------------------------------------- render
  const k = view.k;
  const stroke = 1.4 / Math.sqrt(k);
  const touches = (a: string, b: string) => Boolean(active && (a === active || b === active));
  const pinned = sim.nodes.some((node) => node.fx != null);
  const dragging = gesture.current?.kind === "drag" && gesture.current.moved;
  const focusNode = focus ? nodeById.get(focus) : undefined;

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      role="group"
      aria-label="Catalog graph. Plus and minus zoom, 0 fits everything, arrow keys pan, Escape clears the selection."
      onKeyDown={onKeyDown}
      className={cn(
        "relative w-full overflow-hidden rounded-[var(--radius-md)] border border-line bg-surface-sunken outline-none focus-visible:ring-2 focus-visible:ring-accent-ghost",
        className,
      )}
    >
      <svg
        ref={svgRef}
        width={size.width}
        height={size.height}
        className={cn("block touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")}
        role="img"
        aria-label="Engine catalog dependency graph. Scroll to zoom, drag to pan, click an engine for details."
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={() => setHover(null)}
      >
        <rect width={size.width} height={size.height} fill="transparent" onPointerDown={onBackgroundDown} />

        <g transform={`translate(${view.x},${view.y}) scale(${k})`}>
          {/* Substitute edges: dashed, no arrow. These engines COMPETE. */}
          {showSubstitutes
            ? data.substitute_edges.map((edge, index) => {
                const from = simById.get(edge.source);
                const to = simById.get(edge.target);
                if (!from || !to) return null;
                const lit = touches(edge.source, edge.target);
                const hovered = hover?.kind === "substitute" && hover.index === index;
                return (
                  <g key={"sub-" + index}>
                    <line
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke="var(--color-replay)"
                      strokeWidth={(edge.coverage === "full" ? 1.1 : 0.75) * stroke * (hovered ? 1.8 : 1)}
                      strokeDasharray={`${3 * stroke} ${4 * stroke}`}
                      opacity={hovered ? 0.95 : lit ? 0.7 : neighbourhood ? 0.05 : 0.24}
                    />
                    <line
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke="transparent"
                      strokeWidth={10 / k}
                      onPointerEnter={() => !gesture.current && setHover({ kind: "substitute", index })}
                      onPointerLeave={() => setHover(null)}
                    />
                  </g>
                );
              })
            : null}

          {/* Dependency edges: solid, arrowed. These engines CHAIN. */}
          {data.dependency_edges.map((edge, index) => {
            const from = simById.get(edge.source);
            const to = simById.get(edge.target);
            if (!from || !to) return null;
            const lit = touches(edge.source, edge.target);
            const hovered = hover?.kind === "dependency" && hover.index === index;
            const geometry = dependencyGeometry(from, to);
            const head = 6 / Math.sqrt(k);
            const { x: ux, y: uy } = geometry.direction;
            const tip = geometry.tip;
            const arrow = [
              `${tip.x},${tip.y}`,
              `${tip.x - ux * head - uy * head * 0.55},${tip.y - uy * head + ux * head * 0.55}`,
              `${tip.x - ux * head + uy * head * 0.55},${tip.y - uy * head - ux * head * 0.55}`,
            ].join(" ");
            const opacity = hovered ? 1 : lit ? 0.95 : neighbourhood ? 0.08 : 0.55;
            const colour = lit || hovered ? "var(--color-accent-strong)" : "var(--color-accent)";
            return (
              <g key={"dep-" + index}>
                <path
                  d={geometry.d}
                  fill="none"
                  stroke={colour}
                  strokeWidth={stroke * (hovered ? 2 : lit ? 1.5 : 1)}
                  opacity={opacity}
                />
                <polygon points={arrow} fill={colour} opacity={opacity} />
                <path
                  d={geometry.d}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={12 / k}
                  onPointerEnter={() => !gesture.current && setHover({ kind: "dependency", index })}
                  onPointerLeave={() => setHover(null)}
                />
              </g>
            );
          })}

          {sim.nodes.map((node) => {
            const info = nodeById.get(node.id);
            if (!info) return null;
            const faded = Boolean(neighbourhood && !neighbourhood.has(node.id));
            const isFocus = node.id === focus;
            const isHover = node.id === hoveredNode;
            const degree = info.in_degree + info.out_degree;
            const showLabel =
              k >= LABEL_ZOOM || isFocus || isHover || degree >= 3 || Boolean(neighbourhood?.has(node.id));
            return (
              <g
                key={node.id}
                transform={`translate(${node.x},${node.y})`}
                className="cursor-pointer"
                opacity={faded ? 0.18 : 1}
                onPointerDown={(event) => onNodeDown(event, node.id)}
                onPointerEnter={() => !gesture.current && setHover({ kind: "node", id: node.id })}
                onPointerLeave={() => setHover(null)}
              >
                <circle r={node.radius + 10} fill="transparent" />
                {isFocus || isHover ? (
                  <circle
                    r={node.radius + 5}
                    fill="none"
                    stroke="var(--color-accent)"
                    strokeWidth={1.5 / Math.sqrt(k)}
                    opacity={isFocus ? 1 : 0.6}
                  />
                ) : null}
                {node.fx != null ? (
                  <circle
                    r={node.radius + 3}
                    fill="none"
                    stroke="var(--color-ink-subtle)"
                    strokeWidth={1 / Math.sqrt(k)}
                    strokeDasharray={`${2 / Math.sqrt(k)} ${2 / Math.sqrt(k)}`}
                  />
                ) : null}
                <circle
                  r={node.radius}
                  fill={
                    info.pii_risk === "high"
                      ? "var(--color-danger)"
                      : degree > 0
                        ? "var(--color-accent)"
                        : "var(--color-ink-subtle)"
                  }
                  stroke="var(--color-surface-sunken)"
                  strokeWidth={1.4 / Math.sqrt(k)}
                />
                {showLabel ? (
                  <text
                    y={node.radius + 13 / k}
                    textAnchor="middle"
                    className="mono pointer-events-none"
                    fontSize={10.5 / k}
                    fontWeight={isFocus || isHover ? 600 : 400}
                    fill={isFocus || isHover ? "var(--color-ink)" : "var(--color-ink-muted)"}
                    stroke="var(--color-surface-sunken)"
                    strokeWidth={3.5 / k}
                    strokeLinejoin="round"
                    paintOrder="stroke"
                  >
                    {node.id}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>
      </svg>

      {/* ------------------------------------------------------- toolbar */}
      <div className="absolute left-3 top-3 flex items-start gap-1.5">
        <form
          className="relative"
          onSubmit={(event) => {
            event.preventDefault();
            if (matches[0]) choose(matches[0].id);
          }}
        >
          <Search className="pointer-events-none absolute left-2.5 top-[9px] size-3.5 text-ink-subtle" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setQuery("");
            }}
            placeholder="Find an engine"
            aria-label="Find an engine"
            className="h-8 w-52 rounded-[var(--radius-sm)] border border-line bg-surface/90 pl-8 pr-2 text-[12px] text-ink backdrop-blur placeholder:text-ink-subtle focus-visible:border-accent-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ghost"
          />
          {matches.length ? (
            <ul className="absolute left-0 top-9 z-10 w-64 overflow-hidden rounded-[var(--radius-sm)] border border-line bg-surface shadow-float">
              {matches.map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    onClick={() => choose(node.id)}
                    className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left hover:bg-surface-raised"
                  >
                    <span className="mono truncate text-[12px] text-ink">{node.id}</span>
                    <span className="truncate text-[10.5px] text-ink-subtle">{node.tags[0]}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </form>

        <div className="flex h-8 items-center rounded-[var(--radius-sm)] border border-line bg-surface/90 backdrop-blur">
          <Button variant="ghost" size="icon-sm" aria-label="Zoom out" title="Zoom out (-)" onClick={() => zoomBy(1 / 1.3)}>
            <Minus />
          </Button>
          <span className="mono w-11 text-center text-[11px] tabular text-ink-muted">{Math.round(k * 100)}%</span>
          <Button variant="ghost" size="icon-sm" aria-label="Zoom in" title="Zoom in (+)" onClick={() => zoomBy(1.3)}>
            <Plus />
          </Button>
        </div>
        <Button
          variant="outline"
          size="icon-sm"
          className="h-8 w-8 bg-surface/90 backdrop-blur"
          aria-label="Fit to view"
          title="Fit to view (0)"
          onClick={fitAll}
        >
          <Maximize2 />
        </Button>
        {pinned ? (
          <Button variant="outline" size="sm" className="h-8 bg-surface/90 backdrop-blur" onClick={resetLayout}>
            <RotateCcw />
            Reset layout
          </Button>
        ) : null}
      </div>

      {/* --------------------------------------------------------- tooltip */}
      {hover && !dragging ? (
        <HoverCard
          hover={hover}
          data={data}
          nodeById={nodeById}
          adjacency={adjacency}
          pointer={pointer}
          bounds={size}
        />
      ) : null}

      {/* --------------------------------------------------- details panel */}
      {focusNode ? (
        <DetailsPanel
          node={focusNode}
          data={data}
          showSubstitutes={showSubstitutes}
          onSelect={onSelect}
          onClear={onClear}
          onOpen={onOpen}
        />
      ) : null}

      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-1.5 rounded-[var(--radius-sm)] border border-line bg-surface/90 px-2.5 py-2 backdrop-blur">
        <LegendRow
          sample={
            <svg width="26" height="8">
              <line x1="0" y1="4" x2="20" y2="4" stroke="var(--color-accent)" strokeWidth="1.4" />
              <path d="M20 1 L25 4 L20 7 Z" fill="var(--color-accent)" />
            </svg>
          }
          label="dependency - engines chain"
        />
        <LegendRow
          sample={
            <svg width="26" height="8">
              <line
                x1="0"
                y1="4"
                x2="26"
                y2="4"
                stroke="var(--color-replay)"
                strokeWidth="1.1"
                strokeDasharray="3 4"
              />
            </svg>
          }
          label="substitute - engines compete"
        />
        <LegendRow
          sample={
            <svg width="26" height="8">
              <circle cx="13" cy="4" r="3.4" fill="var(--color-danger)" />
            </svg>
          }
          label="high PII risk"
        />
      </div>

      <p className="pointer-events-none absolute bottom-3 right-3 hidden text-[10.5px] text-ink-subtle md:block">
        Scroll to zoom · drag to pan · drag an engine to move it · click for details
      </p>
    </div>
  );
}

// ------------------------------------------------------------- hover card
function HoverCard({
  hover,
  data,
  nodeById,
  adjacency,
  pointer,
  bounds,
}: {
  hover: NonNullable<Hover>;
  data: CatalogGraphData;
  nodeById: Map<string, GraphNode>;
  adjacency: { dependencies: Map<string, Set<string>>; substitutes: Map<string, Set<string>> };
  pointer: Point;
  bounds: { width: number; height: number };
}) {
  let body: React.ReactNode = null;
  if (hover.kind === "node") {
    const node = nodeById.get(hover.id);
    if (!node) return null;
    body = (
      <>
        <p className="mono text-[12px] font-semibold text-ink">{node.id}</p>
        <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted text-pretty">{node.purpose}</p>
        <div className="mt-2 flex flex-wrap gap-1">
          <Badge tone="outline" className="mono">
            {node.cost} cr
          </Badge>
          <Badge tone={node.pii_risk === "high" ? "danger" : "outline"}>PII {node.pii_risk}</Badge>
          <Badge tone="outline">fresh {node.volatility_prior}</Badge>
          <Badge tone="outline">{node.latency_class} latency</Badge>
        </div>
        <p className="mt-2 text-[11px] text-ink-subtle">
          feeds {node.out_degree} · needs {node.in_degree} · competes with{" "}
          {adjacency.substitutes.get(node.id)?.size ?? 0}
        </p>
      </>
    );
  } else if (hover.kind === "dependency") {
    const edge = data.dependency_edges[hover.index];
    if (!edge) return null;
    body = (
      <>
        <p className="mono text-[12px] font-semibold text-ink">
          {edge.source} <span className="text-accent">→</span> {edge.target}
        </p>
        <p className="mt-1.5 text-[11px] text-ink-subtle">Fills the required parameter</p>
        <p className="mono mt-0.5 break-all text-[11.5px] text-ink">
          {edge.param} <span className="text-ink-subtle">←</span> {edge.field}
        </p>
        <p className="mt-1.5 text-[11px] text-ink-subtle">fan-out hint ×{edge.fan_out_hint}</p>
      </>
    );
  } else {
    const edge = data.substitute_edges[hover.index];
    if (!edge) return null;
    body = (
      <>
        <p className="mono text-[12px] font-semibold text-ink">
          {edge.source} <span className="text-replay">⇄</span> {edge.target}
        </p>
        <div className="mt-1.5">
          <Badge tone="outline">{edge.coverage} coverage</Badge>
        </div>
        {edge.note ? (
          <p className="mt-1.5 line-clamp-4 text-[11.5px] leading-relaxed text-ink-muted text-pretty">
            {edge.note}
          </p>
        ) : null}
      </>
    );
  }

  const width = 280;
  const left = Math.min(pointer.x + 16, bounds.width - width - 8);
  const top = Math.min(pointer.y + 16, bounds.height - 150);
  return (
    <div
      className="pointer-events-none absolute z-20 rounded-[var(--radius-sm)] border border-line bg-surface/95 p-3 shadow-float backdrop-blur"
      style={{ left: Math.max(8, left), top: Math.max(8, top), width }}
    >
      {body}
    </div>
  );
}

// ---------------------------------------------------------- details panel
function DetailsPanel({
  node,
  data,
  showSubstitutes,
  onSelect,
  onClear,
  onOpen,
}: {
  node: GraphNode;
  data: CatalogGraphData;
  showSubstitutes: boolean;
  onSelect?: (engine: string) => void;
  onClear?: () => void;
  onOpen?: (engine: string) => void;
}) {
  const needs = data.dependency_edges.filter((edge) => edge.target === node.id);
  const feeds = data.dependency_edges.filter((edge) => edge.source === node.id);
  // A substitute pair can be listed in both directions; show each rival once.
  const competes = showSubstitutes
    ? [
        ...new Map(
          data.substitute_edges
            .filter((edge) => edge.source === node.id || edge.target === node.id)
            .map((edge) => [edge.source === node.id ? edge.target : edge.source, edge] as const),
        ).values(),
      ]
    : [];

  return (
    <aside
      className="absolute right-3 top-3 z-10 flex max-h-[calc(100%-24px)] w-[300px] flex-col overflow-hidden rounded-[var(--radius-md)] border border-line bg-surface/95 shadow-float backdrop-blur"
      aria-label={"Details for " + node.id}
    >
      <div className="flex items-start justify-between gap-2 border-b border-line px-3.5 py-3">
        <div className="min-w-0">
          <p className="mono truncate text-[13px] font-semibold text-ink">{node.id}</p>
          <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted text-pretty">{node.purpose}</p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Close details" onClick={() => onClear?.()}>
          <X />
        </Button>
      </div>

      <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-3.5 py-3">
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
          <Fact label="Cost" value={node.cost + " cr per call"} />
          <Fact label="PII risk" value={node.pii_risk} danger={node.pii_risk === "high"} />
          <Fact label="Freshness prior" value={node.volatility_prior} />
          <Fact label="Latency" value={node.latency_class} />
        </dl>
        <div className="flex flex-wrap gap-1">
          {node.tags.map((tag) => (
            <Badge key={tag} tone="outline" className="mono">
              {tag}
            </Badge>
          ))}
        </div>

        <EdgeList
          title="Needs"
          empty="No upstream engine. It can be called directly."
          rows={needs.map((edge) => ({
            id: edge.source,
            detail: edge.param + " ← " + edge.field,
          }))}
          onSelect={onSelect}
        />
        <EdgeList
          title="Feeds"
          empty="Nothing chains from it."
          rows={feeds.map((edge) => ({
            id: edge.target,
            detail: edge.param + " ← " + edge.field,
          }))}
          onSelect={onSelect}
        />
        {showSubstitutes ? (
          <EdgeList
            title="Competes with"
            empty="No substitute answers the same capability."
            rows={competes.map((edge) => ({
              id: edge.source === node.id ? edge.target : edge.source,
              detail: edge.coverage + " coverage",
            }))}
            onSelect={onSelect}
          />
        ) : null}
      </div>

      {onOpen ? (
        <div className="border-t border-line px-3.5 py-2.5">
          <Button variant="secondary" size="sm" className="w-full" onClick={() => onOpen(node.id)}>
            Open in Explore
            <ArrowRight />
          </Button>
        </div>
      ) : null}
    </aside>
  );
}

function Fact({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div>
      <dt className="uppercase tracking-[0.06em] text-ink-subtle">{label}</dt>
      <dd className={cn("mono mt-0.5 text-[12px]", danger ? "text-danger" : "text-ink")}>{value}</dd>
    </div>
  );
}

function EdgeList({
  title,
  empty,
  rows,
  onSelect,
}: {
  title: string;
  empty: string;
  rows: { id: string; detail: string }[];
  onSelect?: (engine: string) => void;
}) {
  return (
    <section>
      <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-ink-subtle">
        {title} <span className="mono normal-case tracking-normal">({rows.length})</span>
      </p>
      {rows.length ? (
        <ul className="mt-1.5 space-y-1">
          {rows.map((row, index) => (
            <li key={row.id + index}>
              <button
                type="button"
                onClick={() => onSelect?.(row.id)}
                className="group w-full rounded-[var(--radius-sm)] border border-line px-2.5 py-1.5 text-left transition-colors hover:border-accent-muted hover:bg-surface-raised"
              >
                <span className="mono block truncate text-[12px] text-ink group-hover:text-accent-strong">
                  {row.id}
                </span>
                <span className="mono block truncate text-[10.5px] text-ink-subtle">{row.detail}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-[11.5px] text-ink-subtle">{empty}</p>
      )}
    </section>
  );
}

function LegendRow({ sample, label }: { sample: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2">
      {sample}
      <span className="text-[10px] text-ink-subtle">{label}</span>
    </div>
  );
}
