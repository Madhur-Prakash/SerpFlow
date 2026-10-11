/**
 * A small force layout for the catalog graph.
 *
 * d3-force would do the job, but the catalog is ~50 nodes and ~100 edges: an
 * O(n^2) pass is trivial at that size, and owning a hundred lines keeps the
 * console bundle free of another dependency. The start positions are seeded
 * from capability tags and the settle runs a fixed number of ticks, so the
 * same catalog always produces the same picture and a reader can find a node
 * where they left it.
 */

export interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Pinned position, set while dragging and after a drop. */
  fx: number | null;
  fy: number | null;
  radius: number;
  collide: number;
}

export interface SimLinkInput {
  source: string;
  target: string;
  distance: number;
  strength: number;
}

interface SimLink {
  source: SimNode;
  target: SimNode;
  distance: number;
  strength: number;
}

const CHARGE = 420;
const CHARGE_RANGE = 420;
const GRAVITY_X = 0.025;
const GRAVITY_Y = 0.045;

export class ForceLayout {
  readonly nodes: SimNode[];
  private readonly links: SimLink[];
  alpha = 1;
  alphaTarget = 0;
  readonly alphaMin = 0.002;
  private readonly alphaDecay = 1 - Math.pow(0.002, 1 / 300);
  private readonly velocityDecay = 0.42;

  constructor(nodes: SimNode[], links: SimLinkInput[]) {
    this.nodes = nodes;
    const byId = new Map(nodes.map((node) => [node.id, node]));
    this.links = links.flatMap((link) => {
      const source = byId.get(link.source);
      const target = byId.get(link.target);
      return source && target && source !== target
        ? [{ source, target, distance: link.distance, strength: link.strength }]
        : [];
    });
  }

  get active(): boolean {
    return this.alpha > this.alphaMin || this.alphaTarget > 0;
  }

  tick(): void {
    this.alpha += (this.alphaTarget - this.alpha) * this.alphaDecay;
    const alpha = this.alpha;
    const nodes = this.nodes;

    // Springs pull linked engines towards their rest distance.
    for (const link of this.links) {
      const { source, target } = link;
      let dx = target.x + target.vx - source.x - source.vx;
      let dy = target.y + target.vy - source.y - source.vy;
      const distance = Math.hypot(dx, dy) || 1e-6;
      const k = ((distance - link.distance) / distance) * alpha * link.strength;
      dx *= k;
      dy *= k;
      target.vx -= dx * 0.5;
      target.vy -= dy * 0.5;
      source.vx += dx * 0.5;
      source.vy += dy * 0.5;
    }

    // Every pair repels within range, and overlapping pairs are pushed apart.
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1e-6) {
          // Coincident nodes: separate them deterministically.
          dx = (j - i) * 0.37;
          dy = (i - j) * 0.29;
          d2 = dx * dx + dy * dy;
        }
        if (d2 < CHARGE_RANGE * CHARGE_RANGE) {
          const f = (CHARGE * alpha) / Math.max(d2, 400);
          a.vx -= dx * f;
          a.vy -= dy * f;
          b.vx += dx * f;
          b.vy += dy * f;
        }
        const min = a.collide + b.collide;
        if (d2 < min * min) {
          const d = Math.sqrt(d2);
          const push = ((min - d) / d) * 0.35;
          a.vx -= dx * push;
          a.vy -= dy * push;
          b.vx += dx * push;
          b.vy += dy * push;
        }
      }
    }

    // A weak pull to the centre, stronger vertically to suit a wide panel.
    for (const node of nodes) {
      node.vx -= node.x * GRAVITY_X * alpha;
      node.vy -= node.y * GRAVITY_Y * alpha;
    }

    for (const node of nodes) {
      if (node.fx != null && node.fy != null) {
        node.x = node.fx;
        node.y = node.fy;
        node.vx = 0;
        node.vy = 0;
        continue;
      }
      node.vx *= 1 - this.velocityDecay;
      node.vy *= 1 - this.velocityDecay;
      node.x += node.vx;
      node.y += node.vy;
    }
  }

  /** Run to rest synchronously. Used once, before the first paint. */
  settle(maxTicks = 420): void {
    for (let i = 0; i < maxTicks && this.alpha > this.alphaMin; i++) this.tick();
  }
}
