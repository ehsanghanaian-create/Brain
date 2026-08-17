import dagre from '@dagrejs/dagre';
import type { Edge, Node } from '@xyflow/react';
import type { GraphEdge, GraphNode } from '@/lib/api/client';
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
  matched?: boolean;
  [key: string]: unknown;
};
export type SeoFlowNode = Node<SeoNodeData, 'seo'>;
export type Grouping = 'none' | 'type' | 'community';
export type Direction = 'TB' | 'LR' | 'RL';

const NODE_W = 180;
const NODE_H = 46;

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
      type: 'default',
      label: undefined,
      data: { relation: e.relation_type, weight: e.weight, props: e.metadata?.props ?? {} },
      style: { stroke: st.color, strokeWidth: 1.2, strokeDasharray: st.dashed ? '4 3' : undefined, opacity: 0.75 },
      animated: false
    };
  });
}

/** Dagre layered layout (whole graph). Direction TB for content trees, LR for link flows. */
export function layoutLayered(nodes: SeoFlowNode[], edges: Edge[], direction: Direction = 'TB'): SeoFlowNode[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 24, ranksep: 70, marginx: 20, marginy: 20 });
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

/** Grouped layout: one column per group (type or community), nodes sorted by PageRank inside; returns group
 *  background nodes + positioned nodes (React Flow parent/child). */
export function layoutGrouped(nodes: SeoFlowNode[], grouping: Grouping, order?: string[]): Node[] {
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
      draggable: false,
      selectable: false
    } as Node);
    items.forEach((n, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      out.push({ ...n, parentId: groupId, extent: 'parent', position: { x: PAD + c * COL_W, y: TITLE_H + PAD + r * ROW_H } });
    });
    x += w + GAP_X;
  }
  return out;
}
