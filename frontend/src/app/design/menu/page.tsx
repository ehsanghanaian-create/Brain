import type { Metadata } from 'next';
import { PearlMenuPreview } from '@/features/navigation-menu/pearl-menu-preview';

export const metadata: Metadata = { title: 'پیش‌نمایش منوی سالیمور' };

export default async function MenuDesignPage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  return <PearlMenuPreview canvas={params.canvas === '1'} />;
}
