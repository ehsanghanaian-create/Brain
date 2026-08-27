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
  useReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type OnSelectionChangeFunc
} from '@xyflow/react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TYPE_FAMILIES } from '../constants';
import { layoutGrouped, layoutLayered, toFlowEdges, toFlowNodes } from '../layout';
import { GraphToolbar, type ToolbarState } from './graph-toolbar';
import { NodeDetailsPanel } from './node-details-panel';
import { GroupNode, SeoNode } from './seo-node';

const nodeTypes = { seo: SeoNode, group: GroupNode };
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
    siteId: initialSiteId, mode: initialMode, query: '', familyOff: new Set(), relationOff: new Set(), grouping: 'none', direction: 'TB', hideIsolated: true, focusNeighbors: false, limit: 160
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
  const positions = useRef<Map<string, { x: number; y: number }>>(new Map()); // remembers user drags per node
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
        positions.current.clear();
        setSelectedId(null);
        setDetails(null);
        detailsCache.current.clear();
        // default grouping/direction per mode
        setState((s) => ({ ...s, grouping: v.mode.key === 'seo' ? 'type' : 'none', direction: v.mode.key === 'links' ? 'LR' : 'TB', relationOff: new Set(), familyOff: new Set(), focusNeighbors: false }));
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
    else laid = layoutGrouped(flowNodes, state.grouping, view.mode.node_types);
    laid = laid.map((node) => (positions.current.has(node.id) && !node.parentId ? { ...node, position: positions.current.get(node.id)! } : node));
    return { laidNodes: laid, baseEdges: flowEdges };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, hiddenTypes, state.relationOff, state.grouping, state.direction, layoutTick]);

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
    let neighborIds: Set<string> | null = null;
    if (selectedId) {
      neighborIds = new Set([selectedId]);
      baseEdges.forEach((e) => {
        if (e.source === selectedId) neighborIds!.add(e.target);
        if (e.target === selectedId) neighborIds!.add(e.source);
      });
    }
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
          data: { ...node.data, matched: matchIds.has(node.id), dimmed: (!state.focusNeighbors && !!neighborIds && !isNeighbor) || (!!q && !matchIds.has(node.id) && !isNeighbor) }
        };
      });
    const visibleEdges = baseEdges
      .filter((edge) => !focusIds || (focusIds.has(edge.source) && focusIds.has(edge.target)))
      .map((edge) => {
        const connected = !!selectedId && (edge.source === selectedId || edge.target === selectedId);
        return { ...edge, style: { ...edge.style, opacity: neighborIds ? (connected ? 1 : 0.08) : (edge.style?.opacity ?? 0.72), strokeWidth: connected ? 2.4 : 1.1 } };
      });
    return { nodes: visibleNodes, edges: visibleEdges, matches: matchIds.size, neighborCount: Math.max((neighborIds?.size ?? 1) - 1, 0) };
  }, [laidNodes, baseEdges, q, selectedId, state.focusNeighbors]);

  const selectedLabel = useMemo(() => {
    if (!selectedId) return null;
    const node = laidNodes.find((item) => item.id === selectedId);
    return node && node.type === 'seo' ? String((node.data as { label?: string }).label ?? selectedId) : selectedId;
  }, [laidNodes, selectedId]);

  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ padding: 0.15, duration: 300 }), 60);
    return () => clearTimeout(t);
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
        onRelayout={() => { positions.current.clear(); setLayoutTick((t) => t + 1); }}
        onSearchSubmit={onSearchSubmit}
        onResetFilters={() => patch({ familyOff: new Set(), relationOff: new Set() })}
        selectedLabel={selectedLabel} neighborCount={neighborCount} />
      {error && <BackendError error={error} />}
      <div className='grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]'>
        <div className='bg-card relative min-h-[460px] overflow-hidden rounded-xl border shadow-sm' dir='ltr'>
          <div className='pointer-events-none absolute top-3 left-3 z-10 flex items-center gap-2 rounded-lg border bg-background/90 px-2.5 py-1.5 text-[11px] shadow-sm backdrop-blur' dir='rtl'>
            <span><strong>{nodes.filter((node) => node.type === 'seo').length.toLocaleString('fa-IR')}</strong> گره نمایان</span>
            <span className='text-muted-foreground'>•</span>
            <span><strong>{edges.length.toLocaleString('fa-IR')}</strong> رابطه</span>
            {state.focusNeighbors && <Badge variant='secondary'>نمای متمرکز</Badge>}
          </div>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={onNodeClick}
            onSelectionChange={onSelectionChange}
            onNodeDragStop={(_, n) => positions.current.set(n.id, n.position)}
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
