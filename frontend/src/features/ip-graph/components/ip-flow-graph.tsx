'use client';

import '@xyflow/react/dist/style.css';
import { Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, useNodesState, useReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react';
import { IconArrowBackUp, IconFileText, IconHandMove, IconPhoneCall, IconRefresh, IconRoute, IconSparkles, IconUserScan } from '@tabler/icons-react';
import { memo, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { FloatingGlowEdge } from '@/features/network/components/brain-network';
import { useManualLayout } from '@/features/graph/use-manual-layout';
import type { GlowEdgeData } from '@/features/graph/components/glow-edge';
import { endpoints, type IpGraph, type IpGraphNode } from '@/lib/api/client';
import { cn } from '@/lib/utils';

/** Entry-flow graph: source → visitor/IP → landing page → goal (تماس / فرم). `seo` = cookieless tracker (anonymous daily
 *  visitors), `ads` = ads collector (real IPs + click-fraud risk). Same glass/flow language as the knowledge graph. */

type Kind = IpGraphNode['kind'];
const KIND: Record<Kind, { color: string; fa: string; Icon: typeof IconRoute; w: number; h: number; x: number; gap: number }> = {
  source: { color: '#a855f7', fa: 'منبع ورود', Icon: IconRoute, w: 220, h: 48, x: 0, gap: 64 },
  actor: { color: '#22d3ee', fa: 'بازدیدکننده / IP', Icon: IconUserScan, w: 230, h: 54, x: 380, gap: 66 },
  page: { color: '#4f8cff', fa: 'صفحهٔ ورود', Icon: IconFileText, w: 260, h: 48, x: 790, gap: 64 },
  goal: { color: '#22c55e', fa: 'تماس / فرم', Icon: IconPhoneCall, w: 150, h: 54, x: 1200, gap: 90 }
};
const STATUS: Record<string, { color: string; fa: string }> = {
  ok: { color: '#22d3ee', fa: 'عادی' },
  hot: { color: '#22c55e', fa: 'تماس گرفته / تبدیل شده' },
  watch: { color: '#f59e0b', fa: 'زیر نظر' },
  risk: { color: '#ef4444', fa: 'پرخطر (احتمال کلیک تقلبی)' }
};
const fa = new Intl.NumberFormat('fa-IR');
const when = (v: unknown) => (typeof v === 'string' && v ? new Date(v).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' }) : '—');

type CardData = { label: string; sub?: string | null; kind: Kind; status: string; weight: number; dimmed?: boolean; hot?: boolean; [k: string]: unknown };
type CardNode = Node<CardData, 'card'>;
type FlowEdge = Edge<GlowEdgeData, 'net'>;

function CardImpl({ data, selected }: NodeProps<CardNode>) {
  const k = KIND[data.kind];
  const tone = data.kind === 'actor' ? (STATUS[data.status]?.color ?? k.color) : k.color;
  const Icon = k.Icon;
  const lit = selected || data.hot;
  return (
    <div
      dir='rtl'
      className={cn('flex items-center gap-2 rounded-2xl border px-3 py-1.5 text-xs backdrop-blur-md transition-all duration-300', data.dimmed && 'opacity-25', lit && 'scale-[1.05]')}
      style={{ width: k.w, minHeight: k.h, borderColor: `${tone}${lit ? 'ff' : '70'}`, background: 'color-mix(in oklab, var(--card) 74%, transparent)', boxShadow: lit ? `0 0 0 1px ${tone}66, 0 0 28px ${tone}55` : `0 0 12px ${tone}22` }}
    >
      <Handle type='target' position={Position.Left} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type='source' position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
      <span className='grid size-7 shrink-0 place-items-center rounded-full' style={{ background: `${tone}22`, color: tone }}>
        <Icon size={15} />
      </span>
      <div className='min-w-0 flex-1'>
        <div className='truncate font-semibold' dir={data.kind === 'actor' || data.kind === 'page' ? 'ltr' : undefined} style={data.kind === 'page' ? { textAlign: 'right' } : undefined}>
          {data.label}
        </div>
        {data.sub && <div className='text-muted-foreground truncate text-[10px]'>{data.sub}</div>}
      </div>
      <span className='shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums' style={{ background: `${tone}22`, color: tone }}>
        {fa.format(data.weight)}
      </span>
    </div>
  );
}
const nodeTypes = { card: memo(CardImpl) };
const edgeTypes = { net: FloatingGlowEdge };

function layout(g: IpGraph): CardNode[] {
  const cols: Record<Kind, IpGraphNode[]> = { source: [], actor: [], page: [], goal: [] };
  for (const n of g.nodes) cols[n.kind].push(n);
  const tallest = Math.max(...(Object.keys(cols) as Kind[]).map((k) => cols[k].length * KIND[k].gap), 1);
  const out: CardNode[] = [];
  for (const kind of Object.keys(cols) as Kind[]) {
    const k = KIND[kind];
    const top = (tallest - cols[kind].length * k.gap) / 2;
    cols[kind].forEach((n, i) => out.push({ id: n.id, type: 'card', position: { x: k.x, y: top + i * k.gap }, data: { label: n.label, sub: n.sub, kind, status: n.status, weight: n.weight } }));
  }
  return out;
}

function buildEdges(g: IpGraph, flow: boolean, hi: string | null): FlowEdge[] {
  return g.edges.map((e) => {
    const color = e.status === 'risk' ? STATUS.risk.color : e.status === 'watch' ? STATUS.watch.color : e.kind === 'goal' ? STATUS.hot.color : e.kind === 'entry' ? KIND.source.color : KIND.page.color;
    const hot = !!hi && (e.source === hi || e.target === hi);
    const heavy = Math.min(4, 1 + Math.floor(Math.log2(e.weight + 1)));
    return {
      id: e.id, source: e.source, target: e.target, type: 'net' as const,
      data: { active: flow && (!hi || hot), color, particles: heavy, speed: Math.max(2.6, 5.6 - heavy * 0.7), strong: hot || e.kind === 'goal', weight: e.weight },
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color },
      style: { stroke: color, strokeWidth: hot ? 2.2 : 1 + Math.min(2, e.weight * 0.15), strokeOpacity: hi && !hot ? 0.1 : 0.7 }
    };
  });
}

function Refit({ count }: { count: number }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    // nodes arrive after mount and are measured asynchronously: fit once early and once when everything has a size
    const timers = [120, 700].map((ms) => setTimeout(() => fitView({ padding: 0.08, duration: 350 }), ms));
    return () => timers.forEach(clearTimeout);
  }, [fitView, count]);
  useEffect(() => {
    const on = () => fitView({ padding: 0.08, duration: 300 });
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, [fitView]);
  return null;
}

function Row({ k, v, ltr }: { k: string; v: React.ReactNode; ltr?: boolean }) {
  if (v === undefined || v === null || v === '') return null;
  return (
    <div className='flex items-start justify-between gap-3'>
      <span className='text-muted-foreground'>{k}</span>
      <span className='truncate text-end' dir={ltr ? 'ltr' : undefined}>{v}</span>
    </div>
  );
}

function Details({ node, scope, siteId, onClose }: { node: IpGraphNode; scope: 'seo' | 'ads'; siteId: string; onClose: () => void }) {
  const m = node.meta as Record<string, unknown>;
  const tone = node.kind === 'actor' ? (STATUS[node.status]?.color ?? KIND.actor.color) : KIND[node.kind].color;
  const reasons = Array.isArray(m.risk_reasons) ? (m.risk_reasons as string[]) : [];
  return (
    <div className='rounded-2xl border p-3 text-xs' style={{ borderColor: `${tone}66`, boxShadow: `inset 0 0 40px ${tone}0d` }}>
      <div className='mb-2 flex items-center justify-between gap-2'>
        <div className='flex min-w-0 items-center gap-2'>
          <span className='size-2.5 shrink-0 rounded-full' style={{ background: tone }} />
          <span className='truncate font-semibold' dir='ltr'>{node.label}</span>
          <span className='text-muted-foreground shrink-0'>· {KIND[node.kind].fa}{node.kind === 'actor' ? ` · ${STATUS[node.status]?.fa ?? ''}` : ''}</span>
        </div>
        <button type='button' className='text-muted-foreground hover:text-foreground shrink-0' onClick={onClose}>بستن</button>
      </div>
      {node.kind !== 'actor' ? (
        <Row k='تعداد ورود / رویداد در این نما' v={fa.format(node.weight)} />
      ) : scope === 'ads' ? (
        <div className='grid gap-1 sm:grid-cols-2'>
          <Row k='شهر / کشور' v={[m.city, m.country].filter(Boolean).join('، ')} />
          <Row k='اینترنت (ISP)' v={m.isp as string} ltr />
          <Row k='ورود به سایت' v={`${fa.format(Number(m.landings ?? 0))} (از تبلیغ: ${fa.format(Number(m.ads_landings ?? 0))})`} />
          <Row k='کلیک تماس' v={fa.format(Number(m.tel_clicks ?? 0))} />
          <Row k='نشست‌ها / رویدادها' v={`${fa.format(Number(m.sessions ?? 0))} / ${fa.format(Number(m.events ?? 0))}`} />
          <Row k='امتیاز ریسک' v={`${fa.format(Number(m.risk_score ?? 0))} از ۱۰۰`} />
          <Row k='اولین مشاهده' v={when(m.first_seen)} />
          <Row k='آخرین مشاهده' v={when(m.last_seen)} />
          {(m.hosting || m.proxy) ? <Row k='زمینه' v={[m.hosting ? 'دیتاسنتر/هاستینگ' : '', m.proxy ? 'پروکسی/VPN' : ''].filter(Boolean).join(' · ')} /> : null}
        </div>
      ) : (
        <div className='grid gap-1 sm:grid-cols-2'>
          <Row k='دستگاه / کشور' v={[m.device, m.country].filter(Boolean).join(' · ')} ltr />
          <Row k='نشست‌ها / صفحه‌ها' v={`${fa.format(Number(m.sessions ?? 0))} / ${fa.format(Number(m.pages ?? 0))}`} />
          <Row k='تبدیل (تماس/فرم)' v={fa.format(Number(m.conversions ?? 0))} />
          <Row k='بیشترین ماندگاری' v={`${fa.format(Number(m.duration_s ?? 0))} ثانیه · اسکرول ${fa.format(Number(m.max_scroll ?? 0))}٪`} />
          <Row k='آخرین مشاهده' v={when(m.last_seen)} />
        </div>
      )}
      {reasons.length > 0 && (
        <div className='mt-2 flex flex-wrap gap-1.5'>
          {reasons.map((r) => (
            <span key={r} className='rounded-full border px-2 py-0.5' style={{ borderColor: `${tone}66`, color: tone }}>{r}</span>
          ))}
        </div>
      )}
      {scope === 'ads' && node.kind === 'actor' && (
        <a className='text-primary mt-2 inline-block underline-offset-4 hover:underline' href={`/ads-data?site=${encodeURIComponent(siteId)}`}>
          باز کردن داشبورد تبلیغات (جزئیات کامل و مسدودسازی IP)
        </a>
      )}
    </div>
  );
}

const PERIODS = [
  { h: 24, fa: '۲۴ ساعت' },
  { h: 72, fa: '۳ روز' },
  { h: 168, fa: '۷ روز' },
  { h: 672, fa: '۲۸ روز' }
];

export function IpFlowGraph({ scope, siteId, defaultHours = 168, height = 600 }: { scope: 'seo' | 'ads'; siteId: string; defaultHours?: number; height?: number }) {
  const [graph, setGraph] = useState<IpGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(defaultHours);
  const [limit, setLimit] = useState(30);
  const [tick, setTick] = useState(0);
  const [flow, setFlow] = useState(true);
  const [focus, setFocus] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<CardNode>([]);
  const manual = useManualLayout(`ip:${scope}:${siteId}`);      // hand-made arrangement per scope + site

  useEffect(() => setHours(defaultHours), [defaultHours]);
  useEffect(() => {
    if (!siteId) return;
    let alive = true;
    setError(null);
    setFocus(null);
    endpoints
      .ipGraph(scope, siteId, hours, limit)
      .then((g) => alive && setGraph(g))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [scope, siteId, hours, limit, tick]);

  const adj = useMemo(() => {
    const m = new Map<string, Set<string>>();
    const add = (a: string, b: string) => (m.get(a) ?? m.set(a, new Set()).get(a))!.add(b);
    for (const e of graph?.edges ?? []) {
      add(e.source, e.target);
      add(e.target, e.source);
    }
    return m;
  }, [graph]);
  const base = useMemo(() => (graph ? manual.apply(layout(graph)) : []), [graph, manual.apply, manual.version]);
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
  const s = (graph?.stats ?? {}) as Record<string, unknown>;
  const empty = !!graph && graph.nodes.length === 0;

  return (
    <div className='space-y-3'>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        {(Object.keys(KIND) as Kind[]).map((k) => (
          <span key={k} className='inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5' style={{ borderColor: `${KIND[k].color}55` }}>
            <span className='size-2 rounded-full' style={{ background: KIND[k].color, boxShadow: `0 0 6px ${KIND[k].color}` }} />
            {k === 'actor' ? (scope === 'ads' ? 'IP' : 'بازدیدکنندهٔ ناشناس') : KIND[k].fa}
          </span>
        ))}
        {(['hot', 'watch', 'risk'] as const).filter((x) => scope === 'ads' || x === 'hot').map((x) => (
          <span key={x} className='inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5' style={{ borderColor: `${STATUS[x].color}55`, color: STATUS[x].color }}>
            {STATUS[x].fa}
          </span>
        ))}
        <span className='ms-auto flex items-center gap-1'>
          <NativeSelect value={String(hours)} onChange={(e) => setHours(Number(e.target.value))} className='h-8 text-xs'>
            {PERIODS.map((p) => <NativeSelectOption key={p.h} value={String(p.h)}>{p.fa}</NativeSelectOption>)}
            {!PERIODS.some((p) => p.h === hours) && <NativeSelectOption value={String(hours)}>{fa.format(Math.round(hours / 24))} روز</NativeSelectOption>}
          </NativeSelect>
          <NativeSelect value={String(limit)} onChange={(e) => setLimit(Number(e.target.value))} className='h-8 text-xs'>
            {[15, 30, 50, 80].map((n) => <NativeSelectOption key={n} value={String(n)}>{fa.format(n)} {scope === 'ads' ? 'IP' : 'بازدیدکننده'}</NativeSelectOption>)}
          </NativeSelect>
          {manual.count > 0 ? (
            <Button size='sm' variant='outline' onClick={manual.reset} title='بازگشت به چیدمان خودکار'>
              <IconArrowBackUp className='size-3.5' /> چیدمان خودکار ({fa.format(manual.count)})
            </Button>
          ) : (
            <span className='text-muted-foreground inline-flex items-center gap-1' title='هر گره را با ماوس بکشید و رها کنید'>
              <IconHandMove className='size-3.5' /> گره‌ها را بکشید
            </span>
          )}
          <Button size='sm' variant={flow ? 'default' : 'outline'} onClick={() => setFlow((v) => !v)}>
            <IconSparkles className='size-3.5' /> جریان
          </Button>
          <Button size='sm' variant='ghost' onClick={() => setTick((t) => t + 1)} title='به‌روزرسانی'>
            <IconRefresh className='size-3.5' />
          </Button>
        </span>
      </div>
      {graph && (
        <p className='text-muted-foreground text-xs'>
          {scope === 'ads'
            ? `${fa.format(Number(s.actors_total ?? 0))} IP فعال · ${fa.format(Number(s.shown ?? 0))} نمایش (پرخطرترها و پرورودترها اول) · ${fa.format(Number(s.landings ?? 0))} ورود · ${fa.format(Number(s.calls ?? 0))} کلیک تماس · ${fa.format(Number(s.risky ?? 0))} IP پرخطر`
            : `${fa.format(Number(s.sessions ?? 0))} نشست · ${fa.format(Number(s.actors_total ?? 0))} بازدیدکننده · ${fa.format(Number(s.conversions ?? 0))} تماس/فرم — ${String(s.note ?? '')}`}
        </p>
      )}
      <div className='bg-background/40 relative overflow-hidden rounded-2xl border' style={{ height }} dir='ltr'>
        {error && <p className='text-destructive absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 text-center text-sm'>{error}</p>}
        {!graph && !error && <p className='text-muted-foreground absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 text-center text-sm'>در حال خواندن ورودی‌ها…</p>}
        {empty && <p className='text-muted-foreground absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 px-6 text-center text-sm' dir='rtl'>در این بازه ورودی ثبت نشده است. {scope === 'seo' ? 'اگر ردیاب هنوز روی سایت نصب نشده، از تب «نصب» شروع کنید.' : 'بازهٔ زمانی را بزرگ‌تر کنید.'}</p>}
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange}
            onNodeClick={(_, n) => setFocus((f) => (f === n.id ? null : n.id))}
            onNodeMouseEnter={(_, n) => setHover(n.id)} onNodeMouseLeave={() => setHover(null)} onPaneClick={() => setFocus(null)}
            onNodeDragStop={(_, n) => manual.remember([n])} onSelectionDragStop={(_, ns) => manual.remember(ns)} nodesDraggable
            fitView fitViewOptions={{ padding: 0.08 }} minZoom={0.1} maxZoom={2} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode='dark'
          >
            <Refit count={base.length} />
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
            <Controls position='bottom-left' showInteractive={false} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
      {selected && <Details node={selected} scope={scope} siteId={siteId} onClose={() => setFocus(null)} />}
    </div>
  );
}
