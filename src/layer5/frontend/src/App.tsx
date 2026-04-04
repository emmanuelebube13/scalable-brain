import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { Overview } from '@/components/views/Overview';
import { Risk } from '@/components/views/Risk';
import { Regimes } from '@/components/views/Regimes';
import { Model } from '@/components/views/Model';
import { Trades } from '@/components/views/Trades';
import { Strategies } from '@/components/views/Strategies';
import { Assets } from '@/components/views/Assets';
import type { ViewType } from '@/types';
import { Toaster } from '@/components/ui/sonner';
import { toast } from 'sonner';

function App() {
  const [activeView, setActiveView] = useState<ViewType>('overview');
  const [isLoading, setIsLoading] = useState(true);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Number keys 1-7 switch views
      if (e.key >= '1' && e.key <= '7') {
        const viewIndex = parseInt(e.key) - 1;
        const views: ViewType[] = ['overview', 'risk', 'regimes', 'model', 'trades', 'strategies', 'assets'];
        if (views[viewIndex]) {
          setActiveView(views[viewIndex]);
        }
      }
      // R to refresh
      if (e.key === 'r' || e.key === 'R') {
        toast.success('Dashboard refreshed');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Initial loading animation
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(false);
      toast.success('Layer 5 Dashboard connected', {
        description: 'Real-time telemetry active',
      });
    }, 800);

    return () => clearTimeout(timer);
  }, []);

  // View change animation
  const handleViewChange = useCallback((view: ViewType) => {
    setActiveView(view);
  }, []);

  // Render active view
  const renderView = () => {
    switch (activeView) {
      case 'overview':
        return <Overview />;
      case 'risk':
        return <Risk />;
      case 'regimes':
        return <Regimes />;
      case 'model':
        return <Model />;
      case 'trades':
        return <Trades />;
      case 'strategies':
        return <Strategies />;
      case 'assets':
        return <Assets />;
      default:
        return <Overview />;
    }
  };

  if (isLoading) {
    return (
      <div className="h-screen w-screen bg-[#0B0C0F] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-cyan-500 to-cyan-600 flex items-center justify-center mx-auto mb-4 animate-pulse">
            <span className="text-[#0B0C0F] font-bold text-2xl">L5</span>
          </div>
          <h1 className="text-xl font-semibold text-[#F3F4F6] mb-2">Layer 5 Dashboard</h1>
          <p className="text-sm text-[#6B7280]">Initializing telemetry...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen bg-[#0B0C0F] flex overflow-hidden">
      {/* Grain Overlay */}
      <div className="grain-overlay" />

      {/* Sidebar */}
      <Sidebar activeView={activeView} onViewChange={handleViewChange} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <TopBar />

        {/* View Content */}
        <main className="flex-1 overflow-auto">
          <div
            key={activeView}
            className="animate-in fade-in slide-in-from-bottom-2 duration-300"
          >
            {renderView()}
          </div>
        </main>
      </div>

      {/* Toast notifications */}
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#14161C',
            border: '1px solid rgba(255,255,255,0.06)',
            color: '#F3F4F6',
          },
        }}
      />
    </div>
  );
}

export default App;
