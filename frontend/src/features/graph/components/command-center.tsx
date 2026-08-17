'use client';

import '@xyflow/react/dist/style.css';

import { BackendError } from '@/components/seo-brain/backend-error';
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
import { layoutGrouped, layoutLayered, toFlowEdges, toFlowNodes, type SeoFlowNode } from '../layout';
import { GraphToolbar, type ToolbarState } from './graph-toolbar';
import { NodeDetailsPanel } from './node-details-panel';
import { GroupNode, SeoNode } from './seo-node';

const nodeTypes = { seo: SeoNode, group: GroupNode };
const DEFAULT_MODES: GraphMode[] = [
  { key: 'seo', title_fa: 'نقشه سئو', description_fa: '', layout: 'force', group_by: 'type', node_types: [], relation_types: [] },
  { key: 'content', title_fa: 'نقشه محتوا', description_fa: '', layout: 'layered', group_by: 'type', node_types: [], relation_types: [] },
  { key: 'links', title_fa: 'نقشه لینک داخلی', description_fa: '', layout: 'force', group_by: 'community', node_types: [], relation_types: [] }
];

export function CommandCenter({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  return (
    <ReactFlowProvider>
      <CommandCenterInner sites={sites} initialSiteId={initialSiteId} />
    </ReactFlowProvider>
  );
}

function CommandCenterInner({ sites, initialSiteId }: { sites: Site[]; initialSiteId: string }) {
  const rf = useReactFlow();
  const [state, setState] = useState<ToolbarState>({
    siteId: initialSiteId, mode: 'seo', query: '', familyOff: new Set(), relationOff: new Set(), grouping: 'none', direction: 'TB', hideIsolated: true, limit: 400
  });
  const [modes, setModes] = useState<GraphMode[]>(DEFAULT_MODES);
  const [view, setView] = useState<GraphView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<NodeDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [layoutTick, setLayoutTick] = useState(0);
  const positions = useRef<Map<string, { x: number; y: number }>>(new Map()); // remembers user drags per node

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
        // default grouping/direction per mode
        setState((s) => ({ ...s, grouping: v.mode.key === 'seo' ? 'type' : 'none', direction: v.mode.key === 'links' ? 'LR' : 'TB', relationOff: new Set(), familyOff: new Set() }));
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

  const { nodes, edges, matches } = useMemo(() => {
    if (!view) return { nodes: [] as Node[], edges: [] as Edge[], matches: 0 };
    const rawNodes = view.nodes.filter((n) => !hiddenTypes.has(n.type));
    const ids = new Set(rawNodes.map((n) => n.id));
    const rawEdges = view.edges.filter((e) => !state.relationOff.has(e.relation_type) && ids.has(e.source) && ids.has(e.target));
    let flowNodes = toFlowNodes(rawNodes);
    const flowEdges = toFlowEdges(rawEdges);
    // search: mark matches; selection: dim non-neighbours
    const matchIds = new Set<string>();
    if (q) {
      flowNodes.forEach((n) => {
        if (n.data.label.toLowerCase().includes(q) || (n.data.url ?? '').toLowerCase().includes(q) || n.id.toLowerCase().includes(q)) matchIds.add(n.id);
      });
    }
    let neighborIds: Set<string> | null = null;
    if (selectedId) {
      neighborIds = new Set([selectedId]);
      flowEdges.forEach((e) => {
        if (e.source === selectedId) neighborIds!.add(e.target);
        if (e.target === selectedId) neighborIds!.add(e.source);
      });
    }
    flowNodes = flowNodes.map((n) => ({
      ...n,
      selected: n.id === selectedId,
      data: { ...n.data, matched: matchIds.has(n.id), dimmed: (neighborIds ? !neighborIds.has(n.id) : false) || (q ? !matchIds.has(n.id) && !neighborIds?.has(n.id) : false) }
    }));
    const styledEdges = flowEdges.map((e) => ({
      ...e,
      style: { ...e.style, opacity: neighborIds ? (e.source === selectedId || e.target === selectedId ? 1 : 0.08) : (e.style?.opacity ?? 0.75), strokeWidth: neighborIds && (e.source === selectedId || e.target === selectedId) ? 2 : 1.2 }
    }));
    let laid: Node[];
    if (state.grouping === 'none') laid = layoutLayered(flowNodes as SeoFlowNode[], styledEdges, state.direction);
    else laid = layoutGrouped(flowNodes as SeoFlowNode[], state.grouping, view.mode.node_types);
    // keep positions the user dragged (until re-layout)
    laid = laid.map((n) => (positions.current.has(n.id) && !n.parentId ? { ...n, position: positions.current.get(n.id)! } : n));
    return { nodes: laid, edges: styledEdges, matches: matchIds.size };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, hiddenTypes, state.relationOff, state.grouping, state.direction, q, selectedId, layoutTick]);

  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ padding: 0.15, duration: 300 }), 60);
    return () => clearTimeout(t);
  }, [view, state.grouping, state.direction, layoutTick, rf]);

  // details for the selected node
  useEffect(() => {
    if (!selectedId) {
      setDetails(null);
      return;
    }
    let alive = true;
    setDetailsLoading(true);
    setDetailsError(null);
    endpoints
      .nodeDetails(state.siteId, selectedId)
      .then((d) => alive && setDetails(d))
      .catch((e) => alive && setDetailsError(e instanceof ApiError ? `${e.message} (${e.code})` : String(e)))
      .finally(() => alive && setDetailsLoading(false));
    return () => {
      alive = false;
    };
  }, [selectedId, state.siteId]);

  const onNodeClick: NodeMouseHandler = useCallback((_, n) => {
    if (n.type === 'group') return;
    setSelectedId((cur) => (cur === n.id ? null : n.id));
  }, []);
  const onSelectionChange: OnSelectionChangeFunc = useCallback(({ nodes: sel }) => {
    if (sel.length === 0) setSelectedId(null);
  }, []);
  const focusNode = useCallback(
    (id: string) => {
      setSelectedId(id);
      const n = rf.getNode(id);
      if (n) rf.fitView({ nodes: [{ id }], duration: 400, maxZoom: 1.4 });
    },
    [rf]
  );
  const onSearchSubmit = useCallback(() => {
    if (!q) return;
    const first = nodes.find((n) => (n.data as { matched?: boolean }).matched);
    if (first) focusNode(first.id);
  }, [q, nodes, focusNode]);

  return (
    <div className='flex h-[calc(100vh-11rem)] min-h-[560px] flex-col gap-2'>
      <GraphToolbar sites={sites} modes={modes} view={view} state={state} onChange={patch} loading={loading} matches={matches}
        onFit={() => rf.fitView({ padding: 0.15, duration: 300 })}
        onRelayout={() => { positions.current.clear(); setLayoutTick((t) => t + 1); }}
        onSearchSubmit={onSearchSubmit} />
      {error && <BackendError error={error} />}
      <div className='grid min-h-0 flex-1 gap-2 lg:grid-cols-[1fr_360px]'>
        <div className='bg-card min-h-[420px] overflow-hidden rounded-lg border' dir='ltr'>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={onNodeClick}
            onSelectionChange={onSelectionChange}
            onNodeDragStop={(_, n) => positions.current.set(n.id, n.position)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            minZoom={0.05}
            maxZoom={2.5}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
            colorMode='dark'
          >
            <Background gap={24} size={1} />
            <Controls position='bottom-left' showInteractive={false} />
            <MiniMap pannable zoomable position='bottom-right' nodeColor={(n) => ((n.data as { color?: string })?.color ?? '#64748b')} maskColor='rgba(0,0,0,0.5)' />
          </ReactFlow>
        </div>
        <div className='min-h-[320px]'>
          <NodeDetailsPanel details={details} loading={detailsLoading} error={detailsError} onClose={() => setSelectedId(null)} onFocus={focusNode} />
        </div>
      </div>
    </div>
  );
}
