'use client';

import '@xyflow/react/dist/style.css';
import { Background, Controls, MarkerType, Position, ReactFlow, type Edge, type Node } from '@xyflow/react';
import { useEffect, useMemo, useState } from 'react';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { commandApi, type CommandWorkItem } from '../api';

export function WorkGraph({ items, projects, onWork }: {
  items: CommandWorkItem[]; projects: { site_id: string; name: string }[];
  onWork: (item: CommandWorkItem) => void;
}) {
  const [projectId, setProjectId] = useState('');
  const [projectItems, setProjectItems] = useState<CommandWorkItem[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => { if (!projectId && projects.length) setProjectId(projects[0].site_id); }, [projectId, projects]);
  useEffect(() => { if (!projectId) return; let active = true; setLoading(true);
    void commandApi.overview({ site_id: projectId, limit: 500 }).then((data) => { if (active) setProjectItems(data.items); })
      .catch(() => { if (active) setProjectItems(items.filter((item) => item.site_id === projectId)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, items]);
  const visible = useMemo(() => projectItems.filter((item) => !item.deleted_at).slice(0, 35), [projectItems]);
  const { nodes, edges } = useMemo(() => {
    const owners = [...new Map(visible.filter((item) => item.owner_id).map((item) => [item.owner_id!, item.owner_name || 'مسئول'])).entries()];
    const creators = [...new Map(visible.filter((item) => item.created_by_id).map((item) => [item.created_by_id!, item.created_by_name || 'واگذارکننده'])).entries()];
    const nodes: Node[] = [];
    creators.forEach(([id, name], index) => nodes.push({ id: `creator-${id}`, position: { x: 0, y: index * 100 }, sourcePosition: Position.Right,
      data: { label: `واگذارکننده · ${name}` }, style: { border: '1px solid #8b5cf6', borderRadius: 12, background: '#f5f3ff', width: 170, padding: 9, fontSize: 12 } }));
    visible.forEach((item, index) => nodes.push({ id: `work-${item.id}`, position: { x: 270, y: index * 82 }, sourcePosition: Position.Right, targetPosition: Position.Left,
      data: { label: item.title }, style: { border: `1px solid ${item.status === 'blocked' ? '#ef4444' : item.priority === 'critical' ? '#f97316' : '#1abb9c'}`,
        borderRadius: 12, background: '#f8fafc', color: '#0f172a', width: 225, padding: 9, fontSize: 12 } }));
    owners.forEach(([id, name], index) => nodes.push({ id: `owner-${id}`, position: { x: 610, y: index * 100 }, targetPosition: Position.Left,
      data: { label: `مسئول اجرا · ${name}` }, style: { border: '1px solid #0ea5e9', borderRadius: 12, background: '#e0f2fe', width: 180, padding: 9, fontSize: 12 } }));
    const edges: Edge[] = [];
    visible.forEach((item) => {
      if (item.created_by_id) edges.push({ id: `assigned-${item.id}`, source: `creator-${item.created_by_id}`, target: `work-${item.id}`,
        type: 'smoothstep', style: { stroke: '#8b5cf6' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#8b5cf6' } });
      if (item.owner_id) edges.push({ id: `executes-${item.id}`, source: `work-${item.id}`, target: `owner-${item.owner_id}`,
        type: 'smoothstep', style: { stroke: '#0ea5e9' }, markerEnd: { type: MarkerType.ArrowClosed, color: '#0ea5e9' } });
    });
    return { nodes, edges };
  }, [visible]);
  return <div className='space-y-3'>
    <div className='flex flex-wrap items-center gap-3'><NativeSelect aria-label='پروژهٔ گراف' value={projectId} onChange={(event) => setProjectId(event.target.value)} className='min-w-48'>
      {projects.map((project) => <NativeSelectOption key={project.site_id} value={project.site_id}>{project.name}</NativeSelectOption>)}
    </NativeSelect><span className='text-muted-foreground text-xs'>بنفش: واگذاری به کار · آبی: کار به مسئول اجرا · حداکثر ۳۵ کارت برای اجرای روان</span></div>
    {loading ? <div className='flex h-[450px] items-center justify-center rounded-xl border text-sm'>در حال بارگیری گراف…</div> : !visible.length ?
      <div className='text-muted-foreground flex h-[450px] items-center justify-center rounded-xl border border-dashed text-sm'>برای این پروژه هنوز کاری ثبت نشده است.</div> :
      <div className='h-[520px] overflow-hidden rounded-xl border bg-slate-50 dark:bg-slate-950' dir='ltr'>
        <ReactFlow nodes={nodes} edges={edges} fitView onlyRenderVisibleElements nodesDraggable={false} nodesConnectable={false}
          elementsSelectable={false} zoomOnScroll={false} minZoom={0.2} maxZoom={1.4}
          onNodeClick={(_, node) => { if (node.id.startsWith('work-')) { const item = visible.find((row) => row.id === Number(node.id.slice(5))); if (item) onWork(item); } }}>
          <Background gap={26} color='#cbd5e1' /><Controls />
        </ReactFlow>
      </div>}
  </div>;
}
