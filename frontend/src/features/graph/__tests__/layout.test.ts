import { describe, expect, it } from 'vitest';
import type { GraphEdge, GraphNode } from '@/lib/api/client';
import { layoutGrouped, layoutLayered, toFlowEdges, toFlowNodes } from '../layout';

const nodes: GraphNode[] = [
  { id: 'site:t', site_id: 't', type: 'SITE', metadata: { label: 'T', pagerank: 0.5 } },
  { id: 'page:https://t/a', site_id: 't', type: 'PAGE', metadata: { label: 'A', url: 'https://t/a', pagerank: 0.2, community: 1, props: { internal_links_in: 3, gsc_position: 7.94 } } },
  { id: 'query:x', site_id: 't', type: 'QUERY', metadata: { label: 'امداد', pagerank: null, community: 1, props: { position: 8.2, impressions: 100 } } },
  { id: 'problem:orphan', site_id: 't', type: 'SEO_PROBLEM', metadata: { label: 'orphan', props: { severity: 'high', count: 3 } } }
];
const edges: GraphEdge[] = [
  { source: 'site:t', target: 'page:https://t/a', relation_type: 'HAS_PAGE', weight: 1, metadata: {}, site_id: 't' },
  { source: 'page:https://t/a', target: 'query:x', relation_type: 'RANKS_FOR', weight: 0.5, metadata: { props: { position: 8.2 } }, site_id: 't' }
];

describe('graph mapping', () => {
  it('maps nodes with type colours and per-type metrics', () => {
    const fn = toFlowNodes(nodes);
    expect(fn.map((n) => n.id)).toEqual(nodes.map((n) => n.id));
    expect(fn[1].data.metric).toBe('3 in · #7.9');
    expect(fn[2].data.metric).toBe('#8.2 · 100 imp');
    expect(fn[3].data.metric).toBe('3 high');
    expect(fn[0].data.color).toMatch(/^#/);
  });
  it('maps edges with stable ids and relation styling', () => {
    const fe = toFlowEdges(edges);
    expect(fe[1].id).toBe('page:https://t/a|RANKS_FOR|query:x');
    expect((fe[1].data as { relation: string }).relation).toBe('RANKS_FOR');
    expect(fe[1].style?.stroke).toBeTruthy();
  });
});

describe('layouts', () => {
  it('layered layout assigns distinct positions and respects direction', () => {
    const tb = layoutLayered(toFlowNodes(nodes), toFlowEdges(edges), 'TB');
    const ys = tb.map((n) => n.position.y);
    expect(new Set(tb.map((n) => `${n.position.x},${n.position.y}`)).size).toBe(tb.length);
    // site above page above query in TB
    const y = (id: string) => tb.find((n) => n.id === id)!.position.y;
    expect(y('site:t')).toBeLessThan(y('page:https://t/a'));
    expect(y('page:https://t/a')).toBeLessThan(y('query:x'));
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
  });
  it('grouped layout creates one group per type with children parented to it', () => {
    const out = layoutGrouped(toFlowNodes(nodes), 'type', ['SITE', 'PAGE', 'QUERY', 'SEO_PROBLEM']);
    const groups = out.filter((n) => n.type === 'group');
    expect(groups.map((g) => g.id)).toEqual(['group:SITE', 'group:PAGE', 'group:QUERY', 'group:SEO_PROBLEM']);
    const child = out.find((n) => n.id === 'query:x')!;
    expect(child.parentId).toBe('group:QUERY');
    expect((groups[0].data as { label: string }).label).toContain('(1)');
  });
  it('community grouping buckets by community id', () => {
    const out = layoutGrouped(toFlowNodes(nodes), 'community');
    expect(out.filter((n) => n.type === 'group').map((g) => g.id).sort()).toEqual(['group:community:1', 'group:community:—']);
  });
});
