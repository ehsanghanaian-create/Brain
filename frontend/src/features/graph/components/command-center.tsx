'use client';

import '@xyflow/react/dist/style.css';

import { BackendError } from '@/components/seo-brain/backend-error';
import { Badge } from '@/components/ui/badge';
import { ApiError, endpoints, type GraphView, type NodeDetails, type PortfolioOverview, type Site } from '@/lib/api/client';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type OnSelectionChangeFunc
} from '@xyflow/react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import { TYPE_FAMILIES } from '../constants';
import { layoutCircle, layoutForce, layoutGrouped, layoutLayered, layoutRadial, toFlowEdges, toFlowNodes } from '../layout';
import { useManualLayout } from '../use-manual-layout';
import { GlowEdge } from './glow-edge';
import { GraphToolbar, type ToolbarState } from './graph-toolbar';
import { GraphMission } from './graph-mission';
import { NodeDetailsPanel } from './node-details-panel';
import { GroupNode, SeoNode } from './seo-node';

const nodeTypes = { seo: SeoNode, group: GroupNode };
const edgeTypes = { glow: GlowEdge };
const FLOW_EDGE_CAP = 160;   // «جریان ارتباط‌ها»: particles on every edge only while the graph is small enough to stay smooth
export function CommandCenter({ sites, portfolio, initialSiteId, initialMode = 'seo', focusNodeId }: { sites: Site[]; portfolio?: PortfolioOverview | null; initialSiteId: string; initialMode?: ToolbarState['mode']; focusNodeId?: string | null }) {
  return (
    <ReactFlowProvider>
      <CommandCenterInner sites={sites} portfolio={portfolio ?? null} initialSiteId={initialSiteId} initialMode={initialMode} focusNodeId={focusNodeId} />
    </ReactFlowProvider>
  );
}

function CommandCenterInner({ sites, portfolio, initialSiteId, initialMode = 'seo', focusNodeId }: { sites: Site[]; portfolio: PortfolioOverview | null; initialSiteId: string; initialMode?: ToolbarState['mode']; focusNodeId?: string | null }) {
  const rf = useReactFlow();
  const { resolvedTheme } = useTheme();
  const [state, setState] = useState<ToolbarState>({
    siteId: initialSiteId, mode: initialMode, query: '', familyOff: new Set(), relationOff: new Set(), grouping: 'none', direction: 'TB', hideIsolated: false, focusNeighbors: false, limit: 160, flow: false
  });
  const [view, setView] = useState<GraphView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(focusNodeId ?? null);
  const [details, setDetails] = useState<NodeDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [layoutTick, setLayoutTick] = useState(0);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [animating, setAnimating] = useState(false);
  // drag & drop: every (site, mode, layout) keeps its own hand-made arrangement, in this browser, across reloads
  const manual = useManualLayout(`kg:${state.siteId}:${state.mode}:${state.grouping}:${state.direction}`);
  const detailsCache = useRef<Map<string, NodeDetails>>(new Map());

  const patch = useCallback((p: Partial<ToolbarState>) => setState((s) => ({ ...s, ...p })), []);
  const navigateGraph = useCallback((p: Partial<ToolbarState>) => {
    if (p.siteId || p.mode) {
      const url = new URL(window.location.href);
      if (p.siteId) url.searchParams.set('site', p.siteId);
      if (p.mode) url.searchParams.set('mode', p.mode);
      window.history.replaceState(window.history.state, '', url);
    }
    patch(p);
  }, [patch]);

  // load view when site / mode / hideIsolated changes
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setView(null);
    setError(null);
    setSelectedId(null);
    setDetails(null);
    endpoints
      .graphView(state.siteId, { mode: state.mode, limit: state.limit, include_isolated: !(state.mode === 'links' && state.hideIsolated) })
      .then((v) => {
        if (!alive) return;
        setView(v);
        setSelectedId(state.siteId === initialSiteId && state.mode === initialMode && focusNodeId && v.nodes.some((node) => node.id === focusNodeId) ? focusNodeId : null);
        setDetails(null);
        detailsCache.current.clear();
        // default grouping/direction per mode
        setState((s) => ({ ...s, grouping: v.mode.key === 'seo' ? 'type' : v.mode.layout === 'force' ? 'force' : 'none', direction: v.mode.key === 'links' ? 'LR' : 'TB', relationOff: new Set(), familyOff: new Set(), focusNeighbors: false }));
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e), null, '-')))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [state.siteId, state.mode, state.hideIsolated, state.limit, initialSiteId, initialMode, focusNodeId]);

  // filtered + laid-out flow elements
  const hiddenTypes = useMemo(() => new Set(TYPE_FAMILIES.filter((f) => state.familyOff.has(f.key)).flatMap((f) => f.types)), [state.familyOff]);
  const q = state.query.trim().toLowerCase();

  const { laidNodes, baseEdges } = useMemo(() => {
    if (!view) return { laidNodes: [] as Node[], baseEdges: [] as Edge[] };
    const rawNodes = view.nodes.filter((n) => !hiddenTypes.has(n.type));
    const ids = new Set(rawNodes.map((n) => n.id));
    const rawEdges = view.edges.filter((e) => !state.relationOff.has(e.relation_type) && ids.has(e.source) && ids.has(e.target));
    const flowNodes = toFlowNodes(rawNodes);
    const flowEdges = toFlowEdges(rawEdges);
    let laid: Node[];
    if (state.grouping === 'none') laid = layoutLayered(flowNodes, flowEdges, state.direction);
    else if (state.grouping === 'radial') laid = layoutRadial(flowNodes, flowEdges);
    else if (state.grouping === 'force') laid = layoutForce(flowNodes, flowEdges);
    else if (state.grouping === 'circle') laid = layoutCircle(flowNodes);
    else laid = layoutGrouped(flowNodes, state.grouping, view.mode.node_types);
    laid = manual.apply(laid);   // hand-placed nodes win over the automatic layout
    return { laidNodes: laid, baseEdges: flowEdges };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, hiddenTypes, state.relationOff, state.grouping, state.direction, layoutTick, manual.apply, manual.version]);

  // Search and focus only restyle the existing layout; no expensive Dagre pass.
  const { nodes, edges, matches, neighborCount } = useMemo(() => {
    const matchIds = new Set<string>();
    if (q) {
      laidNodes.forEach((node) => {
        if (node.type !== 'seo') return;
        const data = node.data as { label: string; url?: string | null };
        if (data.label.toLowerCase().includes(q) || (data.url ?? '').toLowerCase().includes(q) || node.id.toLowerCase().includes(q)) matchIds.add(node.id);
      });
    }
    const neighborsOf = (id: string) => {
      const set = new Set([id]);
      baseEdges.forEach((e) => {
        if (e.source === id) set.add(e.target);
        if (e.target === id) set.add(e.source);
      });
      return set;
    };
    const neighborIds = selectedId ? neighborsOf(selectedId) : null;
    const hoverIds = hoverId && hoverId !== selectedId ? neighborsOf(hoverId) : null;
    const colorOf = new Map(laidNodes.map((node) => [node.id, String((node.data as { color?: string }).color ?? '#94a3b8')]));
    const focusIds = state.focusNeighbors && neighborIds ? neighborIds : null;
    const requiredGroups = new Set(laidNodes.filter((node) => focusIds?.has(node.id) && node.parentId).map((node) => node.parentId!));
    const visibleNodes = laidNodes
      .filter((node) => !focusIds || focusIds.has(node.id) || requiredGroups.has(node.id))
      .map((node) => {
        if (node.type !== 'seo') return node;
        const isNeighbor = neighborIds?.has(node.id) ?? false;
        return {
          ...node,
          selected: node.id === selectedId,
          data: {
            ...node.data,
            matched: matchIds.has(node.id),
            dimmed: (!state.focusNeighbors && !!neighborIds && !isNeighbor) || (!!q && !matchIds.has(node.id) && !isNeighbor),
            faded: !!hoverIds && !hoverIds.has(node.id),
            neighbor: (!!hoverIds && hoverIds.has(node.id) && node.id !== hoverId) || (!!neighborIds && isNeighbor && node.id !== selectedId)
          }
        };
      });
    const scoped = baseEdges.filter((edge) => !focusIds || (focusIds.has(edge.source) && focusIds.has(edge.target)));
    const flowAll = state.flow && scoped.length <= FLOW_EDGE_CAP;
    const visibleEdges = scoped
      .map((edge) => {
        const connected = !!selectedId && (edge.source === selectedId || edge.target === selectedId);
        const hovered = !!hoverId && (edge.source === hoverId || edge.target === hoverId);
        const glow = hovered ? colorOf.get(hoverId!) : connected ? colorOf.get(selectedId!) : undefined;
        const baseOpacity = neighborIds ? (connected ? 1 : 0.08) : Number(edge.style?.opacity ?? 0.72);
        const active = hovered || connected || flowAll;
        return {
          ...edge,
          data: { ...edge.data, active, strong: hovered || connected, color: glow ?? (typeof edge.style?.stroke === 'string' ? edge.style.stroke : undefined), particles: hovered || connected ? 3 : 2, speed: hovered || connected ? 3.6 : 5 },
          style: {
            ...edge.style,
            stroke: glow ?? edge.style?.stroke,
            opacity: hovered ? 1 : hoverIds ? Math.min(baseOpacity, 0.18) : baseOpacity,
            strokeWidth: hovered || connected ? 2.4 : 1.1,
            filter: glow ? `drop-shadow(0 0 4px ${glow})` : undefined,
            transition: 'opacity 200ms, stroke-width 200ms'
          }
        };
      });
    // hand-dragged positions are re-applied here (cheap pass) so a drag never triggers the expensive layout memo
    return { nodes: manual.apply(visibleNodes), edges: visibleEdges, matches: matchIds.size, neighborCount: Math.max((neighborIds?.size ?? 1) - 1, 0) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [laidNodes, baseEdges, q, selectedId, hoverId, state.focusNeighbors, state.flow, manual.apply, manual.tick]);

  // React Flow owns the node list while the user drags; we push our styled/laid-out nodes into it whenever they change
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([]);
  useEffect(() => { setFlowNodes(nodes); }, [nodes, setFlowNodes]);

  const selectedLabel = useMemo(() => {
    if (!selectedId) return null;
    const node = laidNodes.find((item) => item.id === selectedId);
    return node && node.type === 'seo' ? String((node.data as { label?: string }).label ?? selectedId) : selectedId;
  }, [laidNodes, selectedId]);

  useEffect(() => {
    setAnimating(true);
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500;
    const t = setTimeout(() => rf.fitView({ padding: 0.15, duration }), 60);
    const t2 = setTimeout(() => setAnimating(false), 750);
    return () => { clearTimeout(t); clearTimeout(t2); };
  }, [view, state.grouping, state.direction, state.focusNeighbors, layoutTick, rf]);

  // details for the selected node
  useEffect(() => {
    if (!selectedId) {
      setDetails(null);
      return;
    }
    let alive = true;
    const cached = detailsCache.current.get(`${state.siteId}:${selectedId}`);
    if (cached) {
      setDetails(cached);
      setDetailsLoading(false);
      setDetailsError(null);
      return;
    }
    setDetailsLoading(true);
    setDetailsError(null);
    endpoints
      .nodeDetails(state.siteId, selectedId)
      .then((d) => { if (alive) { detailsCache.current.set(`${state.siteId}:${selectedId}`, d); setDetails(d); } })
      .catch((e) => alive && setDetailsError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)))
      .finally(() => alive && setDetailsLoading(false));
    return () => {
      alive = false;
    };
  }, [selectedId, state.siteId]);

  const onNodeClick: NodeMouseHandler = useCallback((_, n) => {
    if (n.type === 'group') return;
    setSelectedId((cur) => { const next = cur === n.id ? null : n.id; if (!next) patch({ focusNeighbors: false }); return next; });
  }, [patch]);
  const onSelectionChange: OnSelectionChangeFunc = useCallback(({ nodes: sel }) => {
    if (sel.length === 0) { setSelectedId(null); patch({ focusNeighbors: false }); }
  }, [patch]);
  const focusNode = useCallback(
    (id: string) => {
      setSelectedId(id);
      patch({ focusNeighbors: false });
      const n = rf.getNode(id);
      if (n) rf.fitView({ nodes: [{ id }], duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 400, maxZoom: 1.4 });
    },
    [rf, patch]
  );
  const onSearchSubmit = useCallback(() => {
    if (!q) return;
    const first = nodes.find((n) => (n.data as { matched?: boolean }).matched);
    if (first) focusNode(first.id);
  }, [q, nodes, focusNode]);

  return (
    <div className='flex flex-col gap-3'>
      <GraphMission site={portfolio?.sites.find((site) => site.site_id === state.siteId) ?? null} siteId={state.siteId} mode={state.mode} view={view} onModeChange={(mode) => navigateGraph({ mode })} />
      <GraphToolbar sites={sites} view={view} state={state} onChange={navigateGraph} loading={loading} matches={matches}
        onFit={() => rf.fitView({ padding: 0.15, duration: 300 })}
        onRelayout={() => { manual.reset(); setLayoutTick((t) => t + 1); }}
        onSearchSubmit={onSearchSubmit}
        onResetFilters={() => patch({ familyOff: new Set(), relationOff: new Set() })}
        selectedLabel={selectedLabel} neighborCount={neighborCount} />
      {error && <BackendError error={error} />}
      <div className='grid min-h-[590px] gap-3 xl:h-[min(75vh,800px)] xl:grid-cols-[minmax(0,1fr)_380px]'>
        <div className={`bg-card relative min-h-[460px] overflow-hidden rounded-xl border shadow-sm ${animating ? 'graph-animating' : ''}`} dir='ltr'>
          {view && view.nodes.length > 0 && <div className='pointer-events-none absolute top-3 left-3 z-10 flex items-center gap-2 rounded-lg border bg-background/90 px-2.5 py-1.5 text-[11px] shadow-sm backdrop-blur' dir='rtl'>
            <span><strong>{nodes.filter((node) => node.type === 'seo').length.toLocaleString('fa-IR')}</strong> گره نمایان</span>
            <span className='text-muted-foreground'>•</span>
            <span><strong>{edges.length.toLocaleString('fa-IR')}</strong> رابطه</span>
            <span className='text-muted-foreground'>• فلش: از مبدأ به مقصد</span>
            {state.focusNeighbors && <Badge variant='secondary'>نمای متمرکز</Badge>}
            {manual.count > 0 ? (
              <>
                <span className='text-muted-foreground'>•</span>
                <Badge variant='secondary'>{manual.count.toLocaleString('fa-IR')} گره دستی</Badge>
                <button type='button' className='pointer-events-auto text-primary underline-offset-2 hover:underline' onClick={() => { manual.reset(); setLayoutTick((t) => t + 1); }}>
                  چیدمان خودکار
                </button>
              </>
            ) : (
              <>
                <span className='text-muted-foreground'>•</span>
                <span className='text-muted-foreground'>گره‌ها را بکشید تا چیدمان دلخواه بسازید</span>
              </>
            )}
          </div>}
          {view?.nodes.length ? <ReactFlow
            nodes={flowNodes}
            onNodesChange={onNodesChange}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodeClick={onNodeClick}
            onSelectionChange={onSelectionChange}
            onNodeMouseEnter={(_, n) => { if (n.type === 'seo') setHoverId(n.id); }}
            onNodeMouseLeave={() => setHoverId(null)}
            onNodeDragStop={(_, n) => manual.remember([n])}
            onSelectionDragStop={(_, ns) => manual.remember(ns)}
            nodesDraggable
            onPaneClick={() => { setSelectedId(null); patch({ focusNeighbors: false }); }}
            fitView
            minZoom={0.05}
            maxZoom={2.5}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
            colorMode={resolvedTheme === 'dark' ? 'dark' : 'light'}
            onlyRenderVisibleElements
          >
            <Background gap={24} size={1} />
            <Controls position='bottom-left' showInteractive={false} />
            <MiniMap pannable zoomable position='bottom-right' nodeColor={(n) => ((n.data as { color?: string })?.color ?? '#64748b')} maskColor='rgba(0,0,0,0.5)' />
          </ReactFlow> : <div className='flex h-full min-h-[460px] flex-col items-center justify-center p-8 text-center' dir='rtl'>
            <span className='text-muted-foreground mb-3 text-4xl' aria-hidden='true'>◇</span>
            <h3 className='font-semibold'>{loading ? 'در حال ساختن نمای نقشه…' : 'هنوز داده‌ای برای این نمای سایت دیده نمی‌شود'}</h3>
            <p className='text-muted-foreground mt-2 max-w-sm text-sm leading-6'>برای تحلیل رابطهٔ صفحه‌ها و کوئری‌ها، دادهٔ سایت را وصل و پردازش کنید. نبود داده در این نما به معنی نبود مشکل یا فرصت نیست.</p>
            <a href={`/dashboard/sites/${encodeURIComponent(state.siteId)}?tab=integrations`} className='mt-4 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/10'>بررسی اتصال‌ها و داده‌ها ←</a>
          </div>}
        </div>
        <div className='min-h-[320px] xl:min-h-0'>
          <NodeDetailsPanel siteId={state.siteId} mode={state.mode} details={details} loading={detailsLoading} error={detailsError} onClose={() => { setSelectedId(null); patch({ focusNeighbors: false }); }} onFocus={focusNode} />
        </div>
      </div>
    </div>
  );
}
