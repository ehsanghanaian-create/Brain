import PageContainer from '@/components/layout/page-container';
import { ProfileEditor } from '@/features/workspace/components/profile-editor';

export const metadata = { title: 'پروفایل من' };

export default function ProfilePage() {
  return <PageContainer><ProfileEditor /></PageContainer>;
}
