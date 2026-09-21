import dagre from '@dagrejs/dagre';
import { MarkerType, type Edge, type Node } from '@xyflow/react';
import type { GraphEdge, GraphNode } from '@/lib/api/client';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3-force';
import { NODE_STYLE, RELATION_STYLE } from './constants';

export type SeoNodeData = {
  label: string;
  nodeType: string;
  color: string;
  metric?: string;
  url?: string | null;
  pagerank?: number | null;
  community?: number | null;
  dimmed?: boolean;
  faded?: boolean;
  neighbor?: boolean;
  matched?: boolean;
  [key: string]: unknown;
};
export type SeoFlowNode = Node<SeoNodeData, 'seo'>;
/** View modes (Screaming-Frog style): tree, radial, force-directed, circle, or grouped columns. */
export type Grouping = 'none' | 'radial' | 'force' | 'circle' | 'type' | 'community';
export const LAYOUT_FA: Record<Grouping, string> = { none: 'درختی', radial: 'شعاعی', force: 'نیرومحور', circle: 'دایره‌ای', type: 'گروه نوع', community: 'گروه خوشه' };
export type Direction = 'TB' | 'LR' | 'RL';

const NODE_W = 210;
const NODE_H = 58;

function metricFor(n: GraphNode): string | undefined {
  const p = (n.metadata.props ?? {}) as Record<string, unknown>;
  if (n.type === 'QUERY' || n.type === 'KEYWORD') {
    const pos = p.position as number | undefined;
    const imp = p.impressions as number | undefined;
    if (pos != null) return `#${Number(pos).toFixed(1)}${imp != null ? ` · ${imp} imp` : ''}`;
  }
  if (n.type === 'PAGE' || n.type === 'POST' || n.type === 'CATEGORY') {
    const inn = p.internal_links_in as number | undefined;
    const pos = p.gsc_position as number | undefined;
    const parts = [];
    if (inn != null) parts.push(`${inn} in`);
    if (pos != null) parts.push(`#${Number(pos).toFixed(1)}`);
    if (parts.length) return parts.join(' · ');
  }
  if (n.type === 'SEO_PROBLEM') return `${p.count ?? ''} ${p.severity ?? ''}`.trim() || undefined;
  if (n.type === 'SEO_OPPORTUNITY') return p.count != null ? `${p.count}` : undefined;
  return undefined;
}

export function toFlowNodes(nodes: GraphNode[]): SeoFlowNode[] {
  return nodes.map((n) => ({
    id: n.id,
    type: 'seo',
    position: { x: 0, y: 0 },
    data: {
      label: String(n.metadata.label ?? n.id),
      nodeType: n.type,
      color: NODE_STYLE[n.type]?.color ?? '#94a3b8',
      metric: metricFor(n),
      url: n.metadata.url ?? null,
      pagerank: n.metadata.pagerank ?? null,
      community: n.metadata.community ?? null
    },
    width: NODE_W,
    height: NODE_H
  }));
}

export function toFlowEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((e) => {
    const st = RELATION_STYLE[e.relation_type] ?? { color: '#94a3b8' };
    return {
      id: `${e.source}|${e.relation_type}|${e.target}`,
      source: e.source,
      target: e.target,
      type: 'glow',
      label: undefined,
      data: { relation: e.relation_type, weight: e.weight, props: e.metadata?.props ?? {} },
      style: { stroke: st.color, strokeWidth: 1.2, opacity: 0.75 },
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: st.color },
      animated: false
    };
  });
}

/** Dagre layered layout (whole graph). Direction TB for content trees, LR for link flows. */
export function layoutLayered(nodes: SeoFlowNode[], edges: Edge[], direction: Direction = 'TB'): SeoFlowNode[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 34, ranksep: 84, marginx: 28, marginy: 28 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => {
    if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target);
  });
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 } };
  });
}

/** Radial layout: the best-connected node of each component sits in the centre, neighbours on concentric rings (BFS depth). */
export function layoutRadial(nodes: SeoFlowNode[], edges: Edge[]): SeoFlowNode[] {
  if (!nodes.length) return nodes;
  const ids = new Set(nodes.map((n) => n.id));
  const adj = new Map<string, Set<string>>(nodes.map((n) => [n.id, new Set<string>()]));
  edges.forEach((e) => { if (ids.has(e.source) && ids.has(e.target)) { adj.get(e.source)!.add(e.target); adj.get(e.target)!.add(e.source); } });
  const score = (n: SeoFlowNode) => (n.data.pagerank ?? 0) * 1000 + (adj.get(n.id)?.size ?? 0);
  const level = new Map<string, number>();
  const order: string[] = [];
  for (const root of [...nodes].sort((a, b) => score(b) - score(a))) {
    if (level.has(root.id)) continue;
    level.set(root.id, 0);
    const queue = [root.id];
    while (queue.length) {
      const cur = queue.shift()!;
      order.push(cur);
      for (const nb of adj.get(cur) ?? []) if (!level.has(nb)) { level.set(nb, level.get(cur)! + 1); queue.push(nb); }
    }
  }
  const rings = new Map<number, string[]>();
  order.forEach((id) => { const l = level.get(id)!; if (!rings.has(l)) rings.set(l, []); rings.get(l)!.push(id); });
  const pos = new Map<string, { x: number; y: number }>();
  for (const [l, members] of rings) {
    if (l === 0 && members.length === 1) { pos.set(members[0], { x: 0, y: 0 }); continue; }
    const r = Math.max(l * 260, (members.length * (NODE_W + 40)) / (2 * Math.PI));
    members.forEach((id, i) => { const a = (2 * Math.PI * i) / members.length - Math.PI / 2; pos.set(id, { x: r * Math.cos(a), y: r * Math.sin(a) }); });
  }
  return nodes.map((n) => { const p = pos.get(n.id) ?? { x: 0, y: 0 }; return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } }; });
}

/** Force-directed layout (d3-force, run to rest synchronously so the result is stable and drag-able). */
export function layoutForce(nodes: SeoFlowNode[], edges: Edge[]): SeoFlowNode[] {
  if (!nodes.length) return nodes;
  type SN = SimulationNodeDatum & { id: string };
  const sim = nodes.map<SN>((n, i) => ({ id: n.id, x: Math.cos(i * 2.4) * (40 + i * 6), y: Math.sin(i * 2.4) * (40 + i * 6) }));
  const index = new Map(sim.map((s) => [s.id, s]));
  const links = edges.filter((e) => index.has(e.source) && index.has(e.target)).map((e) => ({ source: e.source, target: e.target }));
  const simulation = forceSimulation(sim)
    .force('link', forceLink<SN, SimulationLinkDatum<SN>>(links).id((d) => d.id).distance(160).strength(0.45))
    .force('charge', forceManyBody().strength(-560))
    .force('collide', forceCollide(NODE_W * 0.62))
    .force('center', forceCenter(0, 0))
    .stop();
  const ticks = Math.min(320, 140 + Math.round(nodes.length / 2));
  for (let i = 0; i < ticks; i += 1) simulation.tick();
  return nodes.map((n) => { const s = index.get(n.id)!; return { ...n, position: { x: (s.x ?? 0) - NODE_W / 2, y: (s.y ?? 0) - NODE_H / 2 } }; });
}

/** Circle layout: every node on one ring, ordered by type then PageRank. */
export function layoutCircle(nodes: SeoFlowNode[]): SeoFlowNode[] {
  const sorted = [...nodes].sort((a, b) => a.data.nodeType.localeCompare(b.data.nodeType) || (b.data.pagerank ?? 0) - (a.data.pagerank ?? 0));
  const r = Math.max(320, (sorted.length * (NODE_W + 30)) / (2 * Math.PI));
  return sorted.map((n, i) => { const a = (2 * Math.PI * i) / Math.max(sorted.length, 1) - Math.PI / 2; return { ...n, position: { x: r * Math.cos(a) - NODE_W / 2, y: r * Math.sin(a) - NODE_H / 2 } }; });
}

/** Grouped layout: one column per group (type or community), nodes sorted by PageRank inside; returns group
 *  background nodes + positioned nodes (React Flow parent/child). */
export function layoutGrouped(nodes: SeoFlowNode[], grouping: 'type' | 'community', order?: string[]): Node[] {
  const keyOf = (n: SeoFlowNode) => (grouping === 'community' ? `community:${n.data.community ?? '—'}` : n.data.nodeType);
  const groups = new Map<string, SeoFlowNode[]>();
  nodes.forEach((n) => {
    const k = keyOf(n);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(n);
  });
  const keys = [...groups.keys()].sort((a, b) => {
    if (order) {
      const ia = order.indexOf(a), ib = order.indexOf(b);
      if (ia !== ib) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    }
    return groups.get(b)!.length - groups.get(a)!.length;
  });
  const COLS_PER_GROUP = (n: number) => (n > 24 ? 3 : n > 8 ? 2 : 1);
  const PAD = 16, GAP_X = 40, TITLE_H = 30, ROW_H = NODE_H + 10, COL_W = NODE_W + 12;
  const out: Node[] = [];
  let x = 0;
  for (const k of keys) {
    const items = groups.get(k)!.sort((a, b) => (b.data.pagerank ?? 0) - (a.data.pagerank ?? 0));
    const cols = COLS_PER_GROUP(items.length);
    const rows = Math.ceil(items.length / cols);
    const w = PAD * 2 + cols * COL_W;
    const h = TITLE_H + PAD + rows * ROW_H + PAD;
    const groupId = `group:${k}`;
    const label = grouping === 'community' ? `خوشه ${k.split(':')[1]}` : (NODE_STYLE[k]?.fa ?? k);
    const color = grouping === 'community' ? '#64748b' : (NODE_STYLE[k]?.color ?? '#94a3b8');
    out.push({
      id: groupId,
      type: 'group',
      position: { x, y: 0 },
      data: { label: `${label} (${items.length})` },
      style: { width: w, height: h, background: `${color}14`, border: `1px dashed ${color}88`, borderRadius: 12 },
      draggable: true,        // a whole group can be moved by hand; its members follow
      selectable: false
    } as Node);
    items.forEach((n, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      // deliberately no `extent: 'parent'`: a member may be dragged anywhere, including out of its box
      out.push({ ...n, parentId: groupId, position: { x: PAD + c * COL_W, y: TITLE_H + PAD + r * ROW_H } });
    });
    x += w + GAP_X;
  }
  return out;
}
