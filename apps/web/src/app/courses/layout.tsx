import { TopBar } from '@/components/ui/TopBar';
import { ToastProvider } from '@/components/ui/Toast';

export default function CoursesLayout({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <div className="min-h-screen bg-surface">
        <TopBar />
        {children}
      </div>
    </ToastProvider>
  );
}
