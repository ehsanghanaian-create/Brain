import { describe, expect, it } from 'vitest';
import type { ContentPlan } from '@/lib/api/client';
import { filterPlans, groupByDay, headingsToText, parseHeadings, parseTags, sortPlans, weekDays } from '../lib';

const mk = (o: Partial<ContentPlan>): ContentPlan => ({ id: 1, site_id: 's', content_item_id: null, title: 't', url: null, slug: null, intent: null, serp_intent: null, page_type: null, funnel_stage: null, category_id: null, category_suggested_id: null, category_reason: null, primary_keyword_id: null, primary_keyword: null, secondary_keywords: [], heading_structure: [], seo_title: null, meta_description: null, topic_id: null, cluster_id: null, content_cluster_id: null, search_volume: null, keyword_difficulty: null, priority: null, priority_score: null, ai_priority: null, business_value: null, traffic_opportunity: null, content_gap: null, cannibalization_risk: null, cannibalization: [], ranking_url: null, ranking_position: null, target_audience: null, publish_date: null, publish_time: null, status: 'planned', status_fa: '', page_type_fa: null, intent_fa: null, priority_fa: null, existing_pages: [], link_targets: [], graph_connections: 0, content_score: null, recommendation_id: null, recommendation: {}, publishing: {}, metadata: {}, notes: null, source: null, created_by: null, created_at: '', updated_at: '', allowed_transitions: [], category: null, parent_category: null, category_suggested: null, content_item: null, keywords: [], ...o });

describe('planner helpers', () => {
  it('parses heading structure text in Persian/English forms and round-trips', () => {
    const h = parseHeadings('H2: علائم\nh3 - تهران\n### هزینه\nخط ساده');
    expect(h).toEqual([{ level: 2, text: 'علائم' }, { level: 3, text: 'تهران' }, { level: 2, text: 'هزینه' }, { level: 2, text: 'خط ساده' }]);
    expect(parseHeadings(headingsToText(h))).toEqual(h);
  });
  it('parses tags with Persian and Latin separators', () => { expect(parseTags('a، b, c;d|e')).toEqual(['a', 'b', 'c', 'd', 'e']); });
  it('filters by search/status/category/priority', () => {
    const items = [mk({ id: 1, title: 'امداد خودرو X22', status: 'planned', category_id: 3, priority: 'high', secondary_keywords: ['یدک کش'] }), mk({ id: 2, title: 'گیربکس', status: 'writing', category_id: 4, priority: 'low' })];
    expect(filterPlans(items, { q: 'یدک' }).map((p) => p.id)).toEqual([1]);
    expect(filterPlans(items, { status: 'writing' }).map((p) => p.id)).toEqual([2]);
    expect(filterPlans(items, { category_id: '3', priority: 'high' }).map((p) => p.id)).toEqual([1]);
    expect(filterPlans(items, {})).toHaveLength(2);
  });
  it('sorts numbers desc with nulls last and strings asc', () => {
    const items = [mk({ id: 1, priority_score: 40 }), mk({ id: 2, priority_score: null }), mk({ id: 3, priority_score: 90 })];
    expect(sortPlans(items, 'priority_score', true).map((p) => p.id)).toEqual([3, 1, 2]);
    expect(sortPlans([mk({ id: 1, title: 'ب' }), mk({ id: 2, title: 'الف' })], 'title', false).map((p) => p.id)).toEqual([2, 1]);
  });
  it('groups by day and builds a Saturday-first week', () => {
    const g = groupByDay([{ publish_date: '2026-09-01' }, { publish_date: '2026-09-01' }, { publish_date: null }, { publish_date: '2026-09-03' }]);
    expect(Object.keys(g)).toEqual(['2026-09-01', '2026-09-03']); expect(g['2026-09-01']).toHaveLength(2);
    const w = weekDays(new Date('2026-09-02T00:00:00Z'));    // Wednesday → week starts Saturday 2026-08-29
    expect(w[0]).toBe('2026-08-29'); expect(w).toHaveLength(7); expect(w[6]).toBe('2026-09-04');
  });
});
