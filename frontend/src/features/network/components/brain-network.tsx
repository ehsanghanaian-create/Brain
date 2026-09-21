'use client';

import '@xyflow/react/dist/style.css';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useInternalNode,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type InternalNode,
  type Node,
  type NodeProps
} from '@xyflow/react';
import { IconArrowBackUp, IconBrain, IconChartAreaLine, IconHandMove, IconRefresh, IconSearch, IconSparkles, IconWorld } from '@tabler/icons-react';
import { memo, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { GlowEdge, type GlowEdgeData, type GlowFlowEdge } from '@/features/graph/components/glow-edge';
import { useManualLayout } from '@/features/graph/use-manual-layout';
import { endpoints, type NetworkEdge, type NetworkGraph, type NetworkNode, type NetworkStatus } from '@/lib/api/client';
import { cn } from '@/lib/utils';

/* ------------------------------------------------------------------ palette */

type Kind = NetworkNode['kind'];
const KIND: Record<Kind, { color: string; fa: string; Icon: typeof IconBrain; w: number; h: number }> = {
  brain: { color: '#a855f7', fa: 'مغز', Icon: IconBrain, w: 184, h: 66 },
  provider: { color: '#4f8cff', fa: 'نویسندهٔ هوش مصنوعی', Icon: IconSparkles, w: 178, h: 58 },
  site: { color: '#22d3ee', fa: 'سایت (وردپرس)', Icon: IconWorld, w: 200, h: 58 },
  gsc: { color: '#34d399', fa: 'Search Console', Icon: IconSearch, w: 160, h: 50 },
  ga4: { color: '#f59e0b', fa: 'Google Analytics', Icon: IconChartAreaLine, w: 160, h: 50 }
};
const EDGE_COLOR: Record<NetworkEdge['kind'], string> = { ai: '#4f8cff', wp: '#22d3ee', gsc: '#34d399', ga4: '#f59e0b', backlink: '#e879f9' };
const EDGE_FA: Record<NetworkEdge['kind'], string> = { ai: 'اتصال به مدل', wp: 'اتصال وردپرس', gsc: 'Search Console', ga4: 'GA4', backlink: 'لینک بین سایت‌ها' };
const STATUS: Record<NetworkStatus, { color: string; fa: string }> = {
  ok: { color: '#22c55e', fa: 'متصل' },
  warn: { color: '#f59e0b', fa: 'تنظیم شده، هنوز تست نشده' },
  off: { color: '#64748b', fa: 'وصل نیست' }
};
const OFF = '#64748b';

/* ------------------------------------------------------------------ node */

type NetNodeData = { label: string; kind: Kind; status: NetworkStatus; sub?: string; dimmed?: boolean; hot?: boolean; [k: string]: unknown };
type NetFlowNode = Node<NetNodeData, 'net'>;
type NetFlowEdge = Edge<GlowEdgeData, 'net'>;

function NetNodeImpl({ data, selected }: NodeProps<NetFlowNode>) {
  const k = KIND[data.kind];
  const st = STATUS[data.status];
  const Icon = k.Icon;
  const lit = selected || data.hot;
  return (
    <div
      dir='rtl'
      className={cn('flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs backdrop-blur-md transition-all duration-300', data.dimmed && 'opacity-30', lit && 'scale-[1.05]')}
      style={{
        width: k.w,
        minHeight: k.h,
        borderColor: `${k.color}${lit ? 'ff' : '66'}`,
        background: 'color-mix(in oklab, var(--card) 74%, transparent)',
        boxShadow: lit ? `0 0 0 1px ${k.color}66, 0 0 30px ${k.color}55` : `0 0 14px ${k.color}22`
      }}
    >
      <Handle type='target' position={Position.Top} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type='source' position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
      <span className='grid size-8 shrink-0 place-items-center rounded-full' style={{ background: `${k.color}22`, color: k.color }}>
        <Icon size={16} />
      </span>
      <div className='min-w-0 flex-1'>
        <div className='truncate font-semibold'>{data.label}</div>
        {data.sub && (
          <div className='truncate text-[10px] text-muted-foreground' dir='ltr'>
            {data.sub}
          </div>
        )}
      </div>
      <span className='size-2.5 shrink-0 rounded-full' style={{ background: st.color, boxShadow: `0 0 8px ${st.color}` }} title={st.fa} />
    </div>
  );
}
const NetNode = memo(NetNodeImpl);

/* ------------------------------------------------------------------ floating edge (leaves each box at the point facing the other node) */

function centre(n: InternalNode) {
  const p = n.internals.positionAbsolute;
  return { x: p.x + (n.measured.width ?? 0) / 2, y: p.y + (n.measured.height ?? 0) / 2 };
}
function exit(a: InternalNode, b: InternalNode): { x: number; y: number; side: Position } {
  const ca = centre(a);
  const cb = centre(b);
  const w = (a.measured.width ?? 0) / 2;
  const h = (a.measured.height ?? 0) / 2;
  const dx = cb.x - ca.x;
  const dy = cb.y - ca.y;
  if (!dx && !dy) return { ...ca, side: Position.Top };
  const sx = w / (Math.abs(dx) || 1e-6);
  const sy = h / (Math.abs(dy) || 1e-6);
  const t = Math.min(sx, sy);
  const side = sx < sy ? (dx > 0 ? Position.Right : Position.Left) : dy > 0 ? Position.Bottom : Position.Top;
  return { x: ca.x + dx * t, y: ca.y + dy * t, side };
}

function NetEdgeImpl(props: EdgeProps<NetFlowEdge>) {
  const s = useInternalNode(props.source);
  const t = useInternalNode(props.target);
  if (!s || !t) return null;
  const from = exit(s, t);
  const to = exit(t, s);
  const p = props as unknown as EdgeProps<GlowFlowEdge>;
  return <GlowEdge {...p} sourceX={from.x} sourceY={from.y} targetX={to.x} targetY={to.y} sourcePosition={from.side} targetPosition={to.side} />;
}
const NetEdge = memo(NetEdgeImpl);
/** Floating glow edge (leaves each node at the point facing the other one) — reused by the IP flow graph. */
export const FloatingGlowEdge = NetEdge;

const nodeTypes = { net: NetNode };
const edgeTypes = { net: NetEdge };

/* ------------------------------------------------------------------ layout: Brain in the middle, writers on an inner arc, sites on a ring, GSC/GA4 stacked outward */

function host(u: unknown): string {
  try {
    return typeof u === 'string' && u ? new URL(u).hostname.replace(/^www\./, '') : '';
  } catch {
    return '';
  }
}

function subOf(n: NetworkNode): string | undefined {
  const m = n.meta;
  if (n.kind === 'provider') {
    const days = typeof m.key_days_left === 'number' ? ` · ${m.key_days_left}d` : m.key_expired ? ' · expired' : '';
    return `${(m.model as string) || (m.name as string) || ''}${days}`;
  }
  if (n.kind === 'site') return host(m.wp_url) || host(m.url) || (m.site_id as string);
  if (n.kind === 'gsc' || n.kind === 'ga4') return (m.property as string) || undefined;
  return undefined;
}

function layoutNodes(g: NetworkGraph): NetFlowNode[] {
  const providers = g.nodes.filter((n) => n.kind === 'provider');
  const sites = g.nodes.filter((n) => n.kind === 'site');
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const pos = new Map<string, { x: number; y: number }>();
  const put = (n: NetworkNode | undefined, cx: number, cy: number) => {
    if (n) pos.set(n.id, { x: cx - KIND[n.kind].w / 2, y: cy - KIND[n.kind].h / 2 });
  };
  put(byId.get('brain'), 0, 0);
  const pr = 250;
  providers.forEach((p, i) => {
    const a = providers.length === 1 ? -Math.PI / 2 : -Math.PI * (5 / 6) + (i / (providers.length - 1)) * ((Math.PI * 2) / 3);
    put(p, Math.cos(a) * pr, Math.sin(a) * pr);
  });
  const N = Math.max(sites.length, 1);
  const R = Math.max(450, (N * 240) / (2 * Math.PI));
  sites.forEach((s, i) => {
    const a = Math.PI / 2 + (i / N) * Math.PI * 2 + Math.PI / N;   // start below the Brain so the writers' arc stays clear
    put(s, Math.cos(a) * R, Math.sin(a) * R);
    const sid = String(s.meta.site_id ?? '');
    put(byId.get(`gsc:${sid}`), Math.cos(a) * (R + 180), Math.sin(a) * (R + 180));
    put(byId.get(`ga4:${sid}`), Math.cos(a) * (R + 310), Math.sin(a) * (R + 310));
  });
  return g.nodes.map((n) => ({
    id: n.id,
    type: 'net' as const,
    position: pos.get(n.id) ?? { x: 0, y: 0 },
    data: { label: n.label, kind: n.kind, status: n.status, sub: subOf(n) },
    draggable: true
  }));
}

function buildEdges(g: NetworkGraph, flow: boolean, hi: string | null): NetFlowEdge[] {
  return g.edges.map((e) => {
    const color = e.status === 'off' ? OFF : EDGE_COLOR[e.kind];
    const hot = !!hi && (e.source === hi || e.target === hi);
    const active = flow && e.status !== 'off' && (!hi || hot);
    const particles = e.kind === 'backlink' ? Math.min(4, 1 + e.weight) : e.kind === 'ai' ? 3 : 2;
    const speed = e.kind === 'ai' ? 3.4 : e.kind === 'backlink' ? 4.2 : 5.2;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'net' as const,
      data: { active, color, particles, speed, strong: hot || e.kind === 'ai', relation: e.kind, weight: e.weight },
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color },
      style: {
        stroke: color,
        strokeWidth: hot ? 2.2 : e.kind === 'backlink' ? 1.2 + Math.min(2, e.weight * 0.2) : 1.5,
        strokeOpacity: hi && !hot ? 0.12 : e.status === 'off' ? 0.35 : 0.75
      }
    };
  });
}

/* ------------------------------------------------------------------ details */

function Row({ k, v, ltr }: { k: string; v: React.ReactNode; ltr?: boolean }) {
  if (v === undefined || v === null || v === '') return null;
  return (
    <div className='flex items-start justify-between gap-3'>
      <span className='text-muted-foreground'>{k}</span>
      <span className='truncate text-end' dir={ltr ? 'ltr' : undefined}>
        {v}
      </span>
    </div>
  );
}

function Details({ node, edges, onClose }: { node: NetworkNode; edges: NetworkEdge[]; onClose: () => void }) {
  const m = node.meta;
  const k = KIND[node.kind];
  const mine = edges.filter((e) => e.source === node.id || e.target === node.id);
  return (
    <div className='rounded-2xl border p-3 text-xs' style={{ borderColor: `${k.color}55`, boxShadow: `inset 0 0 40px ${k.color}0d` }}>
      <div className='mb-2 flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <span className='size-2.5 rounded-full' style={{ background: STATUS[node.status].color }} />
          <span className='font-semibold'>{node.label}</span>
          <span className='text-muted-foreground'>· {k.fa}</span>
        </div>
        <button type='button' className='text-muted-foreground hover:text-foreground' onClick={onClose}>
          بستن
        </button>
      </div>
      <div className='grid gap-1 sm:grid-cols-2'>
        <Row k='وضعیت' v={STATUS[node.status].fa} />
        {node.kind === 'provider' && (
          <>
            <Row k='نام' v={m.name as string} ltr />
            <Row k='مدل پیش‌فرض' v={(m.model as string) || '—'} ltr />
            <Row k='کلید' v={m.key_expired ? 'منقضی شده' : typeof m.key_days_left === 'number' ? `${m.key_days_left} روز مانده` : m.configured ? 'ثبت شده' : 'ثبت نشده'} />
          </>
        )}
        {node.kind === 'site' && (
          <>
            <Row k='آدرس' v={(m.url as string) || (m.wp_url as string)} ltr />
            <Row k='حالت' v={(m.mode as string) || '—'} ltr />
            <Row k='مطالب همگام‌شده' v={String(m.posts ?? 0)} />
            <Row k='وردپرس' v={(m.wordpress as string) || 'تنظیم نشده'} ltr />
          </>
        )}
        {(node.kind === 'gsc' || node.kind === 'ga4') && <Row k='پراپرتی' v={(m.property as string) || 'تنظیم نشده'} ltr />}
      </div>
      {mine.length > 0 && (
        <div className='mt-2 flex flex-wrap gap-1.5'>
          {mine.map((e) => (
            <span key={e.id} className='rounded-full border px-2 py-0.5' style={{ borderColor: `${EDGE_COLOR[e.kind]}66`, color: e.status === 'off' ? OFF : EDGE_COLOR[e.kind] }}>
              {EDGE_FA[e.kind]}
              {e.kind === 'backlink' ? ` · ${e.label}` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Re-fit the viewport when the graph arrives or the pane is resized (fitView only runs once on mount by itself). */
function Refit({ count }: { count: number }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.12, duration: 400 }), 80);
    return () => clearTimeout(t);
  }, [fitView, count]);
  useEffect(() => {
    const on = () => fitView({ padding: 0.12, duration: 300 });
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, [fitView]);
  return null;
}

/* ------------------------------------------------------------------ page piece */

export function BrainNetwork() {
  const manual = useManualLayout('network');       // drag & drop arrangement, remembered in this browser
  const [graph, setGraph] = useState<NetworkGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [flow, setFlow] = useState(true);
  const [focus, setFocus] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<NetFlowNode>([]);

  useEffect(() => {
    let alive = true;
    setError(null);
    endpoints
      .network()
      .then((g) => alive && setGraph(g))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [tick]);

  const adj = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of graph?.edges ?? []) {
      (m.get(e.source) ?? m.set(e.source, new Set()).get(e.source))!.add(e.target);
      (m.get(e.target) ?? m.set(e.target, new Set()).get(e.target))!.add(e.source);
    }
    return m;
  }, [graph]);
  const base = useMemo(() => (graph ? manual.apply(layoutNodes(graph)) : []), [graph, manual.apply, manual.version]);
  useEffect(() => setNodes(base), [base, setNodes]);
  const hi = hover ?? focus;
  useEffect(() => {
    setNodes((ns) =>
      ns.map((n) => {
        const near = !!hi && (n.id === hi || !!adj.get(hi)?.has(n.id));
        const dimmed = !!hi && !near;
        return n.data.dimmed === dimmed && n.data.hot === near ? n : { ...n, data: { ...n.data, dimmed, hot: near } };
      })
    );
  }, [hi, adj, setNodes]);
  const edges = useMemo(() => (graph ? buildEdges(graph, flow, hi) : []), [graph, flow, hi]);
  const selected = focus && graph ? (graph.nodes.find((n) => n.id === focus) ?? null) : null;

  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        {(Object.keys(KIND) as Kind[]).map((k) => (
          <span key={k} className='inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5' style={{ borderColor: `${KIND[k].color}55` }}>
            <span className='size-2 rounded-full' style={{ background: KIND[k].color, boxShadow: `0 0 6px ${KIND[k].color}` }} />
            {KIND[k].fa}
          </span>
        ))}
        <span className='inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5' style={{ borderColor: `${EDGE_COLOR.backlink}55` }}>
          <span className='size-2 rounded-full' style={{ background: EDGE_COLOR.backlink, boxShadow: `0 0 6px ${EDGE_COLOR.backlink}` }} />
          لینک بین سایت‌ها
        </span>
        {graph && (
          <span className='text-muted-foreground'>
            {graph.counts.providers} نویسنده · {graph.counts.sites} سایت · {graph.counts.cross_links} مسیر لینک بین سایت‌ها
          </span>
        )}
        <span className='ms-auto flex items-center gap-1'>
          {manual.count > 0 ? (
            <Button size='sm' variant='outline' onClick={manual.reset} title='بازگشت به چیدمان خودکار'>
              <IconArrowBackUp className='size-3.5' /> چیدمان خودکار ({manual.count})
            </Button>
          ) : (
            <span className='text-muted-foreground inline-flex items-center gap-1' title='هر گره را با ماوس بکشید و رها کنید'>
              <IconHandMove className='size-3.5' /> گره‌ها را بکشید
            </span>
          )}
          <Button size='sm' variant={flow ? 'default' : 'outline'} onClick={() => setFlow((v) => !v)}>
            <IconSparkles className='size-3.5' /> جریان ارتباط‌ها
          </Button>
          <Button size='sm' variant='ghost' onClick={() => setTick((t) => t + 1)} title='به‌روزرسانی'>
            <IconRefresh className='size-3.5' />
          </Button>
        </span>
      </div>
      <div className='relative h-[560px] overflow-hidden rounded-2xl border bg-background/40' dir='ltr'>
        {error && <p className='absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 text-center text-sm text-destructive'>{error}</p>}
        {!graph && !error && <p className='absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 text-center text-sm text-muted-foreground'>در حال خواندن شبکه…</p>}
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onNodeClick={(_, n) => setFocus((f) => (f === n.id ? null : n.id))}
            onNodeMouseEnter={(_, n) => setHover(n.id)}
            onNodeMouseLeave={() => setHover(null)}
            onNodeDragStop={(_, n) => manual.remember([n])}
            onSelectionDragStop={(_, ns) => manual.remember(ns)}
            onPaneClick={() => setFocus(null)}
            nodesDraggable
            fitView
            fitViewOptions={{ padding: 0.12 }}
            minZoom={0.15}
            maxZoom={2}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
            colorMode='dark'
          >
            <Refit count={base.length} />
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
            <Controls position='bottom-left' showInteractive={false} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
      {selected && graph && <Details node={selected} edges={graph.edges} onClose={() => setFocus(null)} />}
    </div>
  );
}
