'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Node, XYPosition } from '@xyflow/react';

/** Manual (drag & drop) node positions, remembered per graph view in this browser.
 *
 *  Every view passes its own `key` (site + mode + layout), so an arrangement made in one layout is not imposed on
 *  another one and comes back when the user returns to it. Dragging never re-runs the automatic layout: positions are
 *  kept in a ref and only `version` (load / reset) invalidates the caller's layout memo. */
const PREFIX = 'seo-brain:graph-layout:';
const MAX_NODES = 1500;

type Stored = Record<string, [number, number]>;

export type ManualLayout = {
  /** Overwrite the automatic positions with the ones the user dragged. */
  apply: <T extends Node>(nodes: T[]) => T[];
  /** Remember a drag (one node, or a whole multi-selection). */
  remember: (dragged: { id: string; position: XYPosition }[]) => void;
  /** Forget every manual position for this view and fall back to the automatic layout. */
  reset: () => void;
  count: number;
  /** Changes on load/reset only — put it in the deps of an expensive layout memo. */
  version: number;
  /** Changes on every drag — put it in the deps of a cheap styling memo that re-applies the positions. */
  tick: number;
};

export function useManualLayout(key: string): ManualLayout {
  const map = useRef(new Map<string, XYPosition>());
  const [state, setState] = useState({ count: 0, version: 0, tick: 0 });

  useEffect(() => {
    const next = new Map<string, XYPosition>();
    try {
      const raw = window.localStorage.getItem(PREFIX + key);
      for (const [id, xy] of Object.entries(raw ? (JSON.parse(raw) as Stored) : {})) {
        if (Array.isArray(xy) && Number.isFinite(xy[0]) && Number.isFinite(xy[1])) next.set(id, { x: xy[0], y: xy[1] });
      }
    } catch {
      /* private mode or a corrupt value: just use the automatic layout */
    }
    map.current = next;
    setState((s) => ({ count: next.size, version: s.version + 1, tick: s.tick + 1 }));
  }, [key]);

  const persist = useCallback(() => {
    try {
      if (map.current.size === 0) window.localStorage.removeItem(PREFIX + key);
      else {
        const entries = [...map.current].slice(-MAX_NODES).map(([id, p]) => [id, [Math.round(p.x), Math.round(p.y)]] as const);
        window.localStorage.setItem(PREFIX + key, JSON.stringify(Object.fromEntries(entries)));
      }
    } catch {
      /* quota or private mode: the arrangement still holds for this session */
    }
  }, [key]);

  const remember = useCallback(
    (dragged: { id: string; position: XYPosition }[]) => {
      for (const n of dragged) map.current.set(n.id, { x: n.position.x, y: n.position.y });
      setState((s) => ({ ...s, count: map.current.size, tick: s.tick + 1 })); // no version bump: the layout must not re-run on a drag
      persist();
    },
    [persist]
  );

  const reset = useCallback(() => {
    map.current.clear();
    setState((s) => ({ count: 0, version: s.version + 1, tick: s.tick + 1 }));
    persist();
  }, [persist]);

  const apply = useCallback(
    <T extends Node>(nodes: T[]): T[] =>
      map.current.size === 0
        ? nodes
        : nodes.map((n) => {
            const p = map.current.get(n.id);
            return p ? ({ ...n, position: p } as T) : n;
          }),
    []
  );

  return { apply, remember, reset, count: state.count, version: state.version, tick: state.tick };
}
