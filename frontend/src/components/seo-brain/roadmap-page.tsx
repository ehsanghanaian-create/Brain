import PageContainer from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

/** Placeholder for areas whose phase has not landed yet — shows what it will do and which phase builds it. */
export function RoadmapPage({
  title,
  description,
  phase,
  features
}: {
  title: string;
  description: string;
  phase: string;
  features: string[];
}) {
  return (
    <PageContainer pageTitle={title} pageDescription={description}>
      <Card>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            در دست ساخت <Badge variant='outline'>{phase}</Badge>
          </CardTitle>
          <CardDescription>
            این بخش طبق نقشه راه SEO Brain در فاز مشخص‌شده پیاده‌سازی می‌شود. قابلیت‌های برنامه‌ریزی‌شده:
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className='list-disc space-y-1 ps-5 text-sm'>
            {features.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
