/**
 * The catalog as a graph (section 49).
 *
 * Two edge kinds, drawn so they can never be confused:
 *
 *   dependency  solid, arrowed      how engines CHAIN
 *   substitute  dashed, no arrow    how engines COMPETE
 *
 * The layout is a deterministic force-free placement: engines are grouped by
 * capability tag into rings, so the picture is stable between renders and a
 * reader can find the same node twice.
 */

import { gsap } from "gsap";
import * as React from "react";

import { prefersReducedMotion } from "@/animations";
import { cn } from "@/lib/utils";
import type { CatalogGraph as CatalogGraphData } from "@/types/api";

interface Props {
  data: CatalogGraphData;
  focus?: string | null;
  onSelect?: (engine: string) => void;
  showSubstitutes?: boolean;
  className?: string;
}

interface Placed {
  id: string;
  x: number;
  y: number;
  tag: string;
  degree: number;
  cost: number;
  pii: string;
}

const WIDTH = 1000;
const HEIGHT = 620;

/** Group by primary capability tag, then lay each group out on its own arc. */
function layout(data: CatalogGraphData): Placed[] {
  const byTag = new Map<string, string[]>();
  for (const node of data.nodes) {
    const tag = node.tags[0] ?? "other";
    const bucket = byTag.get(tag) ?? [];
    bucket.push(node.id);
    byTag.set(tag, bucket);
  }

  const tags = [...byTag.keys()].sort(
    (a, b) => (byTag.get(b)?.length ?? 0) - (byTag.get(a)?.length ?? 0),
  );

  const placed: Placed[] = [];
  const centerX = WIDTH / 2;
  const centerY = HEIGHT / 2;

  tags.forEach((tag, tagIndex) => {
    const members = (byTag.get(tag) ?? []).slice().sort();
    const tagAngle = (tagIndex / tags.length) * Math.PI * 2 - Math.PI / 2;
    // Larger groups sit further out so their members do not crowd the centre.
    const groupRadius = 118 + Math.min(members.length, 10) * 11;
    const groupX = centerX + Math.cos(tagAngle) * groupRadius;
    const groupY = centerY + Math.sin(tagAngle) * groupRadius * 0.62;

    members.forEach((id, memberIndex) => {
      const node = data.nodes.find((candidate) => candidate.id === id)!;
      const spread = members.length === 1 ? 0 : (memberIndex / (members.length - 1) - 0.5);
      const localAngle = tagAngle + spread * 0.9;
      const localRadius = members.length === 1 ? 0 : 36 + Math.abs(spread) * 54;
      placed.push({
        id,
        x: groupX + Math.cos(localAngle) * localRadius,
        y: groupY + Math.sin(localAngle) * localRadius * 0.8,
        tag,
        degree: node.in_degree + node.out_degree,
        cost: node.cost,
        pii: node.pii_risk,
      });
    });
  });

  return placed;
}

export function CatalogGraph({
  data,
  focus,
  onSelect,
  showSubstitutes = true,
  className,
}: Props) {
  const svgRef = React.useRef<SVGSVGElement>(null);
  const placed = React.useMemo(() => layout(data), [data]);
  const positions = React.useMemo(
    () => new Map(placed.map((node) => [node.id, node])),
    [placed],
  );

  const neighbours = React.useMemo(() => {
    if (!focus) return null;
    const set = new Set<string>([focus]);
    for (const edge of data.dependency_edges) {
      if (edge.source === focus) set.add(edge.target);
      if (edge.target === focus) set.add(edge.source);
    }
    if (showSubstitutes) {
      for (const edge of data.substitute_edges) {
        if (edge.source === focus) set.add(edge.target);
        if (edge.target === focus) set.add(edge.source);
      }
    }
    return set;
  }, [data, focus, showSubstitutes]);

  React.useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const context = gsap.context(() => {
      const nodes = Array.from(svg.querySelectorAll("[data-node]"));
      const edges = Array.from(svg.querySelectorAll("[data-edge]"));
      if (prefersReducedMotion()) {
        gsap.set([...nodes, ...edges], { opacity: 1, scale: 1 });
        return;
      }
      gsap.fromTo(
        edges,
        { opacity: 0 },
        { opacity: 1, duration: 0.5, stagger: 0.002, ease: "power1.out" },
      );
      gsap.fromTo(
        nodes,
        { opacity: 0, scale: 0.8, transformOrigin: "center" },
        { opacity: 1, scale: 1, duration: 0.4, stagger: 0.008, ease: "back.out(1.4)" },
      );
    }, svg);
    return () => context.revert();
  }, [placed]);

  const dim = (id: string) => Boolean(neighbours && !neighbours.has(id));

  return (
    <div className={cn("relative w-full overflow-hidden rounded-[var(--radius-md)] border border-line bg-surface-sunken", className)}>
      <svg
        ref={svgRef}
        viewBox={"0 0 " + WIDTH + " " + HEIGHT}
        className="h-full w-full"
        role="img"
        aria-label="Engine catalog dependency graph"
      >
        <defs>
          <marker
            id="catalog-arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L8 4 L0 8 z" fill="var(--color-accent-muted)" />
          </marker>
        </defs>

        {/* Substitute edges: dashed, no arrow. These engines COMPETE. */}
        {showSubstitutes
          ? data.substitute_edges.map((edge, index) => {
              const from = positions.get(edge.source);
              const to = positions.get(edge.target);
              if (!from || !to) return null;
              const faded = dim(edge.source) && dim(edge.target);
              return (
                <line
                  key={"sub-" + index}
                  data-edge
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="var(--color-replay)"
                  strokeWidth={edge.coverage === "full" ? 1.1 : 0.7}
                  strokeDasharray="3 4"
                  opacity={faded ? 0.05 : 0.22}
                />
              );
            })
          : null}

        {/* Dependency edges: solid, arrowed. These engines CHAIN. */}
        {data.dependency_edges.map((edge, index) => {
          const from = positions.get(edge.source);
          const to = positions.get(edge.target);
          if (!from || !to) return null;
          const faded = dim(edge.source) && dim(edge.target);
          const midX = (from.x + to.x) / 2;
          const midY = (from.y + to.y) / 2 - 24;
          return (
            <path
              key={"dep-" + index}
              data-edge
              d={"M" + from.x + " " + from.y + " Q" + midX + " " + midY + " " + to.x + " " + to.y}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth={1.4}
              markerEnd="url(#catalog-arrow)"
              opacity={faded ? 0.08 : 0.55}
            />
          );
        })}

        {placed.map((node) => {
          const faded = dim(node.id);
          const isFocus = node.id === focus;
          const radius = 5 + Math.min(node.degree, 6) * 1.2;
          return (
            <g
              key={node.id}
              data-node
              transform={"translate(" + node.x + "," + node.y + ")"}
              className="cursor-pointer"
              onClick={() => onSelect?.(node.id)}
              opacity={faded ? 0.22 : 1}
            >
              <circle
                r={radius + 5}
                fill="transparent"
                stroke={isFocus ? "var(--color-accent)" : "transparent"}
                strokeWidth="1.2"
              />
              <circle
                r={radius}
                fill={
                  node.pii === "high"
                    ? "var(--color-danger)"
                    : node.degree > 0
                      ? "var(--color-accent)"
                      : "var(--color-ink-subtle)"
                }
                stroke="var(--color-ground)"
                strokeWidth="1.4"
              />
              <text
                y={radius + 11}
                textAnchor="middle"
                className="mono pointer-events-none"
                fontSize="8.5"
                fill={isFocus ? "var(--color-ink)" : "var(--color-ink-subtle)"}
              >
                {node.id}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col gap-1.5 rounded-[var(--radius-sm)] border border-line bg-surface/90 px-2.5 py-2 backdrop-blur">
        <LegendRow
          sample={
            <svg width="26" height="8">
              <line
                x1="0"
                y1="4"
                x2="20"
                y2="4"
                stroke="var(--color-accent)"
                strokeWidth="1.4"
              />
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
    </div>
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
