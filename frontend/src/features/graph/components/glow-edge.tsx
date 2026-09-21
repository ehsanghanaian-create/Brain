'use client';

import { BaseEdge, getBezierPath, type Edge, type EdgeProps } from '@xyflow/react';
import { memo } from 'react';

export type GlowEdgeData = { relation?: string; weight?: number; props?: Record<string, unknown>; active?: boolean; strong?: boolean; color?: string; particles?: number; speed?: number; [key: string]: unknown };
export type GlowFlowEdge = Edge<GlowEdgeData, 'glow'>;

/** Deterministic 0..1 per edge id so every edge gets its own particle speed/phase (irregular, never re-randomised). */
function seedOf(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967295;
}

/** Solid bezier edge; when active, tiny glowing dots travel source → target along the same path (SMIL animateMotion —
 *  one element per dot, no per-frame JS and no SVG filters, so a few hundred stay smooth). */
function GlowEdgeImpl({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, data, markerEnd }: EdgeProps<GlowFlowEdge>) {
  const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const active = !!data?.active;
  const color = data?.color ?? (typeof style?.stroke === 'string' ? style.stroke : '#94a3b8');
  const seed = seedOf(id);
  const particles = data?.particles ?? 2;
  const speed = (data?.speed ?? 4.5) * (0.75 + seed * 0.7);
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      {active && (
        <g pointerEvents='none'>
          {data?.strong && <path d={path} fill='none' stroke={color} strokeWidth={5} strokeOpacity={0.14} strokeLinecap='round' />}
          {Array.from({ length: particles }, (_, i) => (
            <circle key={i} r={1.9} fill={color} stroke={color} strokeOpacity={0.28} strokeWidth={4}>
              <animateMotion dur={`${speed.toFixed(2)}s`} begin={`${(-((i + seed) * speed) / particles).toFixed(2)}s`} repeatCount='indefinite' calcMode='linear' path={path} />
            </circle>
          ))}
        </g>
      )}
    </>
  );
}

export const GlowEdge = memo(GlowEdgeImpl);
