'use client';

import '@xyflow/react/dist/style.css';
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from '@xyflow/react';
import { useMemo } from 'react';
import type { CommandWorkItem } from '../api';

export function WorkGraph({ items, onWork }: { items: CommandWorkItem[]; onWork: (item: CommandWorkItem) => void }) {
  const visible = items.slice(0, 35);
  const { nodes, edges } = useMemo(() => {
    const sites = [...new Map(visible.map((item) => [item.site_id, item.site_name || item.site_id])).entries()];
    const owners = [...new Map(visible.filter((item) => item.owner_id).map((item) => [item.owner_id!, item.owner_name || 'مسئول'])).entries()];
    const teams = [...new Map(visible.filter((item) => item.team_id).map((item) => [item.team_id!, item.team_name || 'تیم'])).entries()];
    const result: Node[] = [];
    sites.forEach(([id, name], index) => result.push({ id: `site-${id}`, position: { x: 0, y: index * 116 },
      data: { label: `سایت · ${name}` }, style: { border: '1px solid #0284c7', borderRadius: 14, background: '#e0f2fe', color: '#082f49', width: 185, padding: 10 } }));
    visible.forEach((item, index) => result.push({ id: `work-${item.id}`, position: { x: 275, y: index * 95 },
      data: { label: item.title }, style: { border: `1px solid ${item.status === 'blocked' ? '#ef4444' : item.priority === 'critical' ? '#f97316' : '#1abb9c'}`,
        borderRadius: 14, background: '#f8fafc', color: '#0f172a', width: 235, padding: 10, fontSize: 12 } }));
    owners.forEach(([id, name], index) => result.push({ id: `owner-${id}`, position: { x: 600, y: index * 116 },
      data: { label: `مسئول · ${name}` }, style: { border: '1px solid #8b5cf6', borderRadius: 14, background: '#ede9fe', color: '#2e1065', width: 180, padding: 10 } }));
    teams.forEach(([id, name], index) => result.push({ id: `team-${id}`, position: { x: 870, y: index * 116 },
      data: { label: `تیم · ${name}` }, style: { border: '1px solid #f59e0b', borderRadius: 14, background: '#fef3c7', color: '#78350f', width: 170, padding: 10 } }));
    const links: Edge[] = [];
    visible.forEach((item) => {
      links.push({ id: `site-work-${item.id}`, source: `site-${item.site_id}`, target: `work-${item.id}` });
      if (item.owner_id) links.push({ id: `work-owner-${item.id}`, source: `work-${item.id}`, target: `owner-${item.owner_id}` });
      if (item.team_id) links.push({ id: `work-team-${item.id}`, source: `work-${item.id}`, target: `team-${item.team_id}` });
    });
    return { nodes: result, edges: links.map((edge) => ({ ...edge, type: 'smoothstep', animated: false,
      style: { stroke: '#94a3b8', strokeWidth: 1.5 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' } })) };
  }, [visible]);
  if (!visible.length) return <div className='text-muted-foreground flex h-[460px] items-center justify-center rounded-xl border border-dashed text-sm'>با ثبت نخستین کار، ارتباط سایت، کار، مسئول و تیم اینجا رسم می‌شود.</div>;
  return <div className='space-y-2'>
    <p className='text-muted-foreground text-xs'>روی گرهٔ کار کلیک کنید تا جزئیات و تاریخچه‌اش را ببینید. گراف حداکثر ۳۵ کارِ فیلتر فعلی را نشان می‌دهد.</p>
    <div className='h-[540px] overflow-hidden rounded-xl border bg-slate-50 dark:bg-slate-950' dir='ltr'>
      <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.2} maxZoom={1.5} onNodeClick={(_, node) => {
        if (node.id.startsWith('work-')) { const item = visible.find((row) => row.id === Number(node.id.slice(5))); if (item) onWork(item); }
      }}><Background gap={24} color='#cbd5e1' /><Controls /></ReactFlow>
    </div>
  </div>;
}
