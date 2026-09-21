'use client';

import '@xyflow/react/dist/style.css';

import { BackendError } from '@/components/seo-brain/backend-error';
import { Badge } from '@/components/ui/badge';
import { ApiError, endpoints, type GraphMode, type GraphView, type NodeDetails, type Site } from '@/lib/api/client';
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
import { TYPE_FAMILIES } from '../constants';
import { layoutCircle, layoutForce, layoutGrouped, layoutLayered, layoutRadial, toFlowEdges, toFlowNodes } from '../layout';
import { useManualLayout } from '../use-manual-layout';
import { GlowEdge } from './glow-edge';
import { GraphToolbar, type ToolbarState } from './graph-toolbar';
import { NodeDetailsPanel } from './node-details-panel';
import { GroupNode, SeoNode } from './seo-node';

const nodeTypes = { seo: SeoNode, group: GroupNode };
const edgeTypes = { glow: GlowEdge };
const FLOW_EDGE_CAP = 160;   // «جریان ارتباط‌ها»: particles on every edge only while the graph is small enough to stay smooth
const MAIN_EDGE_CAP = 70;    // always-on flow for the strongest relations (by weight), so link direction reads at a glance
const DEFAULT_MODES: GraphMode[] = [
  { key: 'seo', title_fa: 'نقشه سئو', description_fa: '', layout: 'force', group_by: 'type', node_types: [], relation_types: [] },
  { key: 'content', title_fa: 'نقشه محتوا', description_fa: '', layout: 'layered', group_by: 'type', node_types: [], relation_types: [] },
  { key: 'links', title_fa: 'نقشه لینک داخلی', description_fa: '', layout: 'force', group_by: 'community', node_types: [], relation_types: [] }
];

export function CommandCenter({ sites, initialSiteId, initialMode = 'seo', focusNodeId }: { sites: Site[]; initialSiteId: string; initialMode?: ToolbarState['mode']; focusNodeId?: string | null }) {
  return (
    <ReactFlowProvider>
      <CommandCenterInner sites={sites} initialSiteId={initialSiteId} initialMode={initialMode} focusNodeId={focusNodeId} />
    </ReactFlowProvider>
  );
}

function CommandCenterInner({ sites, initialSiteId, initialMode = 'seo', focusNodeId }: { sites: Site[]; initialSiteId: string; initialMode?: ToolbarState['mode']; focusNodeId?: string | null }) {
  const rf = useReactFlow();
  const [state, setState] = useState<ToolbarState>({
    siteId: initialSiteId, mode: initialMode, query: '', familyOff: new Set(), relationOff: new Set(), grouping: 'none', direction: 'TB', hideIsolated: true, focusNeighbors: false, limit: 160, flow: false
  });
  const [modes, setModes] = useState<GraphMode[]>(DEFAULT_MODES);
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

  // modes (once per site)
  useEffect(() => {
    endpoints.graphModes(state.siteId).then(setModes).catch(() => setModes(DEFAULT_MODES));
  }, [state.siteId]);

  // load view when site / mode / hideIsolated changes
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    endpoints
      .graphView(state.siteId, { mode: state.mode, limit: state.limit, include_isolated: !(state.mode === 'links' && state.hideIsolated) })
      .then((v) => {
        if (!alive) return;
        setView(v);
        setSelectedId(null);
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
  }, [state.siteId, state.mode, state.hideIsolated, state.limit]);

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

  const mainEdgeIds = useMemo(() => {
    const weight = (e: Edge) => Number((e.data as { weight?: number } | undefined)?.weight ?? 0);
    return new Set([...baseEdges].sort((a, b) => weight(b) - weight(a)).slice(0, MAIN_EDGE_CAP).map((e) => e.id));
  }, [baseEdges]);

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
    const calm = !neighborIds && !hoverIds;                       // nothing selected/hovered → ambient flow on the main relations
    const flowAll = state.flow && scoped.length <= FLOW_EDGE_CAP;
    const visibleEdges = scoped
      .map((edge) => {
        const connected = !!selectedId && (edge.source === selectedId || edge.target === selectedId);
        const hovered = !!hoverId && (edge.source === hoverId || edge.target === hoverId);
        const glow = hovered ? colorOf.get(hoverId!) : connected ? colorOf.get(selectedId!) : undefined;
        const baseOpacity = neighborIds ? (connected ? 1 : 0.08) : Number(edge.style?.opacity ?? 0.72);
        const active = hovered || connected || (calm && (flowAll || mainEdgeIds.has(edge.id)));
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
  }, [laidNodes, baseEdges, mainEdgeIds, q, selectedId, hoverId, state.focusNeighbors, state.flow, manual.apply, manual.tick]);

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
    const t = setTimeout(() => rf.fitView({ padding: 0.15, duration: 500 }), 60);
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
      if (n) rf.fitView({ nodes: [{ id }], duration: 400, maxZoom: 1.4 });
    },
    [rf, patch]
  );
  const onSearchSubmit = useCallback(() => {
    if (!q) return;
    const first = nodes.find((n) => (n.data as { matched?: boolean }).matched);
    if (first) focusNode(first.id);
  }, [q, nodes, focusNode]);

  return (
    <div className='flex h-[calc(100vh-10rem)] min-h-[620px] flex-col gap-3'>
      <GraphToolbar sites={sites} modes={modes} view={view} state={state} onChange={patch} loading={loading} matches={matches}
        onFit={() => rf.fitView({ padding: 0.15, duration: 300 })}
        onRelayout={() => { manual.reset(); setLayoutTick((t) => t + 1); }}
        onSearchSubmit={onSearchSubmit}
        onResetFilters={() => patch({ familyOff: new Set(), relationOff: new Set() })}
        selectedLabel={selectedLabel} neighborCount={neighborCount} />
      {error && <BackendError error={error} />}
      <div className='grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]'>
        <div className={`bg-card relative min-h-[460px] overflow-hidden rounded-xl border shadow-sm ${animating ? 'graph-animating' : ''}`} dir='ltr'>
          <div className='pointer-events-none absolute top-3 left-3 z-10 flex items-center gap-2 rounded-lg border bg-background/90 px-2.5 py-1.5 text-[11px] shadow-sm backdrop-blur' dir='rtl'>
            <span><strong>{nodes.filter((node) => node.type === 'seo').length.toLocaleString('fa-IR')}</strong> گره نمایان</span>
            <span className='text-muted-foreground'>•</span>
            <span><strong>{edges.length.toLocaleString('fa-IR')}</strong> رابطه</span>
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
          </div>
          <ReactFlow
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
            colorMode='dark'
            onlyRenderVisibleElements
          >
            <Background gap={24} size={1} />
            <Controls position='bottom-left' showInteractive={false} />
            <MiniMap pannable zoomable position='bottom-right' nodeColor={(n) => ((n.data as { color?: string })?.color ?? '#64748b')} maskColor='rgba(0,0,0,0.5)' />
          </ReactFlow>
        </div>
        <div className='min-h-[320px] xl:min-h-0'>
          <NodeDetailsPanel details={details} loading={detailsLoading} error={detailsError} onClose={() => { setSelectedId(null); patch({ focusNeighbors: false }); }} onFocus={focusNode} />
        </div>
      </div>
    </div>
  );
}
