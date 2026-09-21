'use client';

import { useEffect, useState } from 'react';

type Dot = { dx: number; dy: number; size: number; delay: number; color: string };
type Burst = { id: number; x: number; y: number; dots: Dot[] };
const TARGETS = '[role="tab"], [data-sidebar="menu-button"], [data-slot="tabs-trigger"], [data-slot="toggle-group-item"]';

/** Floating glowing dots around any tab / sidebar item the user clicks — one document listener, CSS-only motion. */
export function SparkleLayer() {
  const [bursts, setBursts] = useState<Burst[]>([]);
  useEffect(() => {
    let n = 0;
    const onClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement | null)?.closest?.(TARGETS);
      if (!target) return;
      const r = target.getBoundingClientRect();
      const x = e.clientX || r.left + r.width / 2;
      const y = e.clientY || r.top + r.height / 2;
      const root = getComputedStyle(document.documentElement);
      const palette = [root.getPropertyValue('--neon-blue').trim() || '#4f8cff', root.getPropertyValue('--neon-purple').trim() || '#a855f7', root.getPropertyValue('--neon-cyan').trim() || '#22d3ee'];
      const dots = Array.from({ length: 12 }, (_, i) => {
        const a = (Math.PI * 2 * i) / 12 + Math.random() * 0.5;
        const d = 16 + Math.random() * 30;
        return { dx: Math.cos(a) * d, dy: Math.sin(a) * d, size: 2.5 + Math.random() * 3.5, delay: Math.random() * 140, color: palette[i % palette.length] };
      });
      const id = ++n;
      setBursts((b) => [...b, { id, x, y, dots }]);
      window.setTimeout(() => setBursts((b) => b.filter((item) => item.id !== id)), 1100);
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);
  if (!bursts.length) return null;
  return (
    <div className='pointer-events-none fixed inset-0 z-[90]' aria-hidden>
      {bursts.map((b) => b.dots.map((d, i) => (
        <span key={`${b.id}-${i}`} className='sparkle-dot' style={{ left: b.x, top: b.y, width: d.size, height: d.size, background: d.color, color: d.color, animationDelay: `${d.delay}ms`, ['--dx' as string]: `${d.dx}px`, ['--dy' as string]: `${d.dy}px` }} />
      )))}
    </div>
  );
}
