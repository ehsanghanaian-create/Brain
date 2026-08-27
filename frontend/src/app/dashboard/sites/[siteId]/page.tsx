import PageContainer from '@/components/layout/page-container';
import { BackendError } from '@/components/seo-brain/backend-error';
import { SiteDetail } from '@/features/sites/components/site-detail';
import { endpoints, settle } from '@/lib/api/client';
import { notFound } from 'next/navigation';
import { cache } from 'react';

const getSite = cache((siteId: string) => settle(endpoints.site(siteId)));

export async function generateMetadata({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = await params;
  const site = await getSite(siteId);
  return { title: site.data ? site.data.name : 'سایت' };
}

export default async function SitePage({ params, searchParams }: { params: Promise<{ siteId: string }>; searchParams: Promise<{ tab?: string }> }) {
  const { siteId } = await params;
  const { tab } = await searchParams;
  const site = await getSite(siteId);
  if (site.error?.status === 404) notFound();
  if (site.error) {
    return (
      <PageContainer pageTitle='سایت'>
        <BackendError error={site.error} />
      </PageContainer>
    );
  }
  const [connections, memory, graph] = await Promise.all([
    settle(endpoints.connections(siteId)),
    settle(endpoints.memory(siteId)),
    settle(endpoints.graphSummary(siteId))
  ]);
  return (
    <PageContainer pageTitle={site.data!.name} pageDescription={`مدیریت سایت، اتصال‌ها و مغز سایت — ${site.data!.canonical_url}`}>
      {connections.error && <BackendError error={connections.error} />}
      <SiteDetail
        site={site.data!}
        connections={connections.data ?? { site_id: siteId, configured: { gsc: null, ga4: null, wordpress: null }, status: {} }}
        memory={memory.data ?? { site_id: siteId, business_rules: [], tone: {}, audience: {}, cta_rules: [], content_rules: [], forbidden_claims: [], successful_patterns: [], updated_at: null }}
        graph={graph.data ?? null}
        initialTab={tab ?? 'overview'}
      />
    </PageContainer>
  );
}
