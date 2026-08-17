'use client';

import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { memo } from 'react';
import { NODE_STYLE } from '../constants';
import type { SeoFlowNode } from '../layout';

function SeoNodeImpl({ data, selected }: NodeProps<SeoFlowNode>) {
  const st = NODE_STYLE[data.nodeType];
  return (
    <div
      className='bg-card text-card-foreground flex h-[46px] w-[180px] items-center gap-2 rounded-lg border px-2 shadow-sm transition-opacity'
      style={{
        borderColor: selected ? data.color : `${data.color}99`,
        boxShadow: selected ? `0 0 0 2px ${data.color}` : data.matched ? `0 0 0 2px ${data.color}66` : undefined,
        opacity: data.dimmed ? 0.25 : 1
      }}
      title={data.url ?? data.label}
      dir='rtl'
    >
      <Handle type='target' position={Position.Top} className='!h-1.5 !w-1.5 !border-0 !bg-transparent' />
      <Handle type='source' position={Position.Bottom} className='!h-1.5 !w-1.5 !border-0 !bg-transparent' />
      <span className='flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white' style={{ background: data.color }} dir='ltr'>
        {st?.short ?? '•'}
      </span>
      <span className='min-w-0 flex-1'>
        <span className='block truncate text-xs font-medium leading-4'>{data.label}</span>
        <span className='text-muted-foreground block truncate text-[10px] leading-3' dir='ltr'>
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
