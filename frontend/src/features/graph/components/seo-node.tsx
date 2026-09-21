'use client';

import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { memo } from 'react';
import { NODE_STYLE } from '../constants';
import type { SeoFlowNode } from '../layout';

function SeoNodeImpl({ data, selected }: NodeProps<SeoFlowNode>) {
  const st = NODE_STYLE[data.nodeType];
  return (
    <div
      className='seo-node bg-card text-card-foreground relative flex h-[58px] w-[210px] items-center gap-2.5 overflow-hidden rounded-xl border px-3 shadow-sm transition-[opacity,box-shadow,transform] duration-200 hover:-translate-y-0.5'
      style={{
        ['--node-color' as string]: data.color,
        borderColor: selected ? data.color : `${data.color}99`,
        boxShadow: selected ? `0 0 0 2px ${data.color}, 0 0 26px -4px ${data.color}` : data.neighbor ? `0 0 0 1px ${data.color}88, 0 0 18px -4px ${data.color}` : data.matched ? `0 0 0 2px ${data.color}66` : undefined,
        opacity: data.dimmed ? 0.25 : data.faded ? 0.45 : 1
      }}
      title={data.url ?? data.label}
      dir='rtl'
    >
      <span className='absolute inset-y-0 right-0 w-1' style={{ background: data.color }} aria-hidden='true' />
      <Handle type='target' position={Position.Top} className='!h-1.5 !w-1.5 !border-0 !bg-transparent' />
      <Handle type='source' position={Position.Bottom} className='!h-1.5 !w-1.5 !border-0 !bg-transparent' />
      <span className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold text-white shadow-sm' style={{ background: data.color }} dir='ltr'>
        {st?.short ?? '•'}
      </span>
      <span className='min-w-0 flex-1'>
        <span className='block truncate text-[13px] font-semibold leading-5'>{data.label}</span>
        <span className='text-muted-foreground block truncate text-[10px] leading-4' dir='ltr'>
          {data.metric ?? st?.fa ?? data.nodeType}
        </span>
      </span>
    </div>
  );
}

export const SeoNode = memo(SeoNodeImpl);

/** Group background node (grouping mode). */
export function GroupNode({ data }: NodeProps<Node<{ label: string }, 'group'>>) {
  return <div className='px-3 pt-1 text-xs font-medium opacity-80'>{data.label}</div>;
}
