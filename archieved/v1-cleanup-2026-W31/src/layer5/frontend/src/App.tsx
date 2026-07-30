import { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense, memo } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { ThemeProvider } from '@/hooks/useTheme';
import type { ViewType, AlertConfig, Granularity } from '@/types';
import { Toaster } from '@/components/ui/sonner';
import { toast } from 'sonner';
import { alertAPI } from '@/services/api';
import { dataCache } from '@/services/dataCache';
import { SettingsModal } from '@/components/modals/SettingsModal';
import { ProfileModal } from '@/components/modals/ProfileModal';

// =============================================================================
// LAZY LOADED VIEWS - Performance optimization
// =============================================================================
const Overview = lazy(() => import('@/components/views/Overview').then(m => ({ default: m.Overview })));
const Risk = lazy(() => import('@/components/views/Risk').then(m => ({ default: m.Risk })));
const Regimes = lazy(() => import('@/components/views/Regimes').then(m => ({ default: m.Regimes })));
const Model = lazy(() => import('@/components/views/Model').then(m => ({ default: m.Model })));
const Trades = lazy(() => import('@/components/views/Trades').then(m => ({ default: m.Trades })));
const Strategies = lazy(() => import('@/components/views/Strategies').then(m => ({ default: m.Strategies })));
const Assets = lazy(() => import('@/components/views/Assets').then(m => ({ default: m.Assets })));
const AlertsView = lazy(() => import('@/components/views/AlertsView').then(m => ({ default: m.AlertsView })));

// Eager load ChartsView as it's the primary interaction point
import { ChartsView } from '@/components/views/ChartsView';

// =============================================================================
// TYPES
// =============================================================================

interface RealTimeTick {
  symbol: string;
  price: number;
  timestamp: string;
  bid: number;
  ask: number;
}

interface OandaStreamTickPayload {
  type: 'tick';
  symbol: string;
  data?: {
    time?: string;
    bid?: number;
    ask?: number;
    mid?: number;
  };
}

interface WebSocketContextType {
  isConnected: boolean;
  lastTick: RealTimeTick | null;
  subscribe: (symbol: string) => void;
  unsubscribe: (symbol: string) => void;
}

// =============================================================================
// WEBSOCKET CONTEXT - Global WebSocket management for OANDA streaming
// =============================================================================

import { createContext, useContext } from 'react';

const WebSocketContext = createContext<WebSocketContextType>({
  isConnected: false,
  lastTick: null,
  subscribe: () => {},
  unsubscribe: () => {},
});

export const useWebSocket = () => useContext(WebSocketContext);

// WebSocket Provider Component
function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastTick, setLastTick] = useState<RealTimeTick | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const subscriptionsRef = useRef<Set<string>>(new Set());
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const MAX_RECONNECT_ATTEMPTS = 5;

  const connect = useCallback(() => {
    // Use environment variable or default to same-origin WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = import.meta.env.VITE_WS_URL || `${protocol}://${window.location.host}/api/v1/streaming/ws/oanda`;
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        toast.success('Real-time feed connected', {
          description: 'OANDA streaming prices active',
          duration: 3000,
        });

        // Resubscribe to all previously subscribed symbols
        subscriptionsRef.current.forEach(symbol => {
          ws.send(JSON.stringify({ type: 'subscribe', symbol, granularity: 'M1' }));
        });
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'tick') {
            const payload = data as OandaStreamTickPayload;
            const bid = Number(payload.data?.bid ?? 0);
            const ask = Number(payload.data?.ask ?? 0);
            const mid = Number(payload.data?.mid ?? ((bid + ask) / 2));
            const tick: RealTimeTick = {
              symbol: payload.symbol,
              bid,
              ask,
              price: mid,
              timestamp: payload.data?.time ?? new Date().toISOString(),
            };
            setLastTick(tick);
          } else if (data.type === 'heartbeat') {
            // Keep connection alive
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        
        // Attempt reconnection if not at max attempts
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current++;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(`Reconnecting... attempt ${reconnectAttemptsRef.current}`);
            connect();
          }, delay);
        } else {
          toast.error('Real-time feed disconnected', {
            description: 'Please refresh to reconnect',
            duration: 5000,
          });
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        toast.error('Connection error', {
          description: 'Real-time feed experiencing issues',
          duration: 3000,
        });
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const subscribe = useCallback((symbol: string) => {
    subscriptionsRef.current.add(symbol);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', symbol, granularity: 'M1' }));
    }
  }, []);

  const unsubscribe = useCallback((symbol: string) => {
    subscriptionsRef.current.delete(symbol);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe', symbol, granularity: 'M1' }));
    }
  }, []);

  // Initialize connection on mount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  const value = useMemo(() => ({
    isConnected,
    lastTick,
    subscribe,
    unsubscribe,
  }), [isConnected, lastTick, subscribe, unsubscribe]);

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

// =============================================================================
// VIEW LOADER - Loading fallback for lazy-loaded components
// =============================================================================

const ViewLoader = memo(() => (
  <div className="h-full w-full flex items-center justify-center">
    <div className="flex flex-col items-center gap-3">
      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500/20 to-cyan-600/20 flex items-center justify-center animate-pulse">
        <span className="text-cyan-500 font-bold text-lg">L5</span>
      </div>
      <p className="text-sm text-muted-foreground">Loading view...</p>
    </div>
  </div>
));

ViewLoader.displayName = 'ViewLoader';

// =============================================================================
// MAIN APP CONTENT
// =============================================================================

function AppContent() {
  // ---------------------------------------------------------------------------
  // CORE STATE
  // ---------------------------------------------------------------------------
  
  // View state
  const [activeView, setActiveView] = useState<ViewType>('overview');
  const [isLoading, setIsLoading] = useState(true);

  // Modal states
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  // Chart state management - simplified for custom chart
  const [selectedSymbol, setSelectedSymbol] = useState('EUR_USD');
  const [selectedTimeframe, setSelectedTimeframe] = useState<Granularity>('1h');

  // Filter by positions
  const [filterByPositions, setFilterByPositions] = useState(false);
  const [openPositions] = useState<string[]>([]);

  // Alerts state
  const [alerts, setAlerts] = useState<AlertConfig[]>([]);
  const [triggeredAlerts, setTriggeredAlerts] = useState<AlertConfig[]>([]);

  const { isConnected, subscribe, unsubscribe } = useWebSocket();

  const handleExport = useCallback(() => {
    toast.info('Export started', {
      description: 'Use view-level export actions for detailed datasets.',
      duration: 3500,
    });
  }, []);

  const handleOpenProfile = useCallback(() => {
    setIsProfileOpen(true);
  }, []);

  const handleOpenSettings = useCallback(() => {
    setIsSettingsOpen(true);
  }, []);

  const handleOpenAuditLogs = useCallback(() => {
    setActiveView('alerts');
    toast.success('Opened alert and audit stream');
  }, []);

  const handleSignOut = useCallback(() => {
    toast.info('Sign out action', {
      description: 'Auth integration is not yet configured in this workspace.',
      duration: 3500,
    });
  }, []);

  // ---------------------------------------------------------------------------
  // EFFECTS
  // ---------------------------------------------------------------------------

  // Initial loading animation and data preload
  useEffect(() => {
    // Start preloading critical data in the background
    dataCache.preloadCriticalData();

    const timer = setTimeout(() => {
      setIsLoading(false);
      toast.success('Layer 5 Dashboard connected', {
        description: 'Real-time telemetry active',
      });
    }, 800);

    return () => clearTimeout(timer);
  }, []);

  // Set up WebSocket subscription when chart view is active
  useEffect(() => {
    if (activeView === 'charts' && selectedSymbol) {
      subscribe(selectedSymbol);
      toast.info(`Subscribed to ${selectedSymbol}`, {
        description: 'Real-time price updates enabled',
        duration: 2000,
      });
      
      return () => {
        unsubscribe(selectedSymbol);
      };
    }
  }, [activeView, selectedSymbol, subscribe, unsubscribe]);

  // Fetch alerts on mount and set up polling
  useEffect(() => {
    void fetchAlerts();
    const interval = setInterval(() => {
      void fetchAlerts();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // ---------------------------------------------------------------------------
  // KEYBOARD SHORTCUTS
  // ---------------------------------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Skip if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Number keys 1-9 for view switching
      if (e.key >= '1' && e.key <= '9') {
        const viewIndex = parseInt(e.key) - 1;
        const views: ViewType[] = [
          'overview', 'charts', 'risk', 'regimes', 'model', 
          'trades', 'strategies', 'assets', 'alerts'
        ];
        if (views[viewIndex]) {
          setActiveView(views[viewIndex]);
          toast.info(`Switched to ${views[viewIndex]}`, { duration: 1000 });
        }
      }

      // R for refresh
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        toast.success('Refreshing data...');
        refreshData();
      }

      // Ctrl/Cmd + number for timeframe quick switch (charts view)
      if ((e.ctrlKey || e.metaKey) && activeView === 'charts') {
        const timeframeMap: Record<string, Granularity> = {
          '1': '1m', '2': '5m', '3': '15m', '4': '30m',
          '5': '1h', '6': '4h', '7': '1d'
        };
        if (timeframeMap[e.key]) {
          e.preventDefault();
          setSelectedTimeframe(timeframeMap[e.key]);
          toast.info(`Timeframe: ${timeframeMap[e.key]}`, { duration: 1500 });
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeView, selectedSymbol, selectedTimeframe]);

  // ---------------------------------------------------------------------------
  // DATA FETCHING FUNCTIONS
  // ---------------------------------------------------------------------------

  const fetchAlerts = async () => {
    try {
      const [allAlerts, triggered] = await Promise.all([
        alertAPI.getAll(),
        alertAPI.getTriggered(),
      ]);
      setAlerts(allAlerts);
      setTriggeredAlerts(triggered);
    } catch {
      // Keep current UI state when alert endpoints are unavailable
    }
  };

  const refreshData = () => {
    void fetchAlerts();
  };

  // ---------------------------------------------------------------------------
  // EVENT HANDLERS
  // ---------------------------------------------------------------------------

  const handleCreateAlert = async (alert: Omit<AlertConfig, 'id' | 'status' | 'created_at'>) => {
    try {
      await alertAPI.create(alert);
      toast.success('Alert created successfully');
      await fetchAlerts();
    } catch {
      toast.error('Failed to create alert');
    }
  };

  const handleDeleteAlert = async (alertId: string) => {
    try {
      await alertAPI.delete(alertId);
      toast.success('Alert deleted');
      await fetchAlerts();
    } catch {
      toast.error('Failed to delete alert');
    }
  };

  const handleSymbolChange = useCallback((symbol: string) => {
    // Unsubscribe from old symbol
    unsubscribe(selectedSymbol);
    // Update symbol
    setSelectedSymbol(symbol);
    toast.info(`Symbol: ${symbol.replace('_', '/')}`, { duration: 1500 });
  }, [selectedSymbol, unsubscribe]);

  const handleTimeframeChange = useCallback((timeframe: string) => {
    setSelectedTimeframe(timeframe as Granularity);
    toast.info(`Timeframe: ${timeframe}`, { duration: 1500 });
  }, []);

  const handleViewChange = useCallback((view: ViewType) => {
    setActiveView(view);
  }, []);

  // ---------------------------------------------------------------------------
  // VIEW RENDERING
  // ---------------------------------------------------------------------------

  const renderView = () => {
    switch (activeView) {
      case 'overview':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Overview onOpenPositionsClick={() => setActiveView('trades')} />
          </Suspense>
        );
      
      case 'charts':
        return (
          <ChartsView
            symbol={selectedSymbol}
            timeframe={selectedTimeframe}
            onSymbolChange={handleSymbolChange}
            onTimeframeChange={handleTimeframeChange}
            filterByPositions={filterByPositions}
            openPositions={openPositions}
          />
        );
      
      case 'risk':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Risk />
          </Suspense>
        );
      
      case 'regimes':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Regimes />
          </Suspense>
        );
      
      case 'model':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Model />
          </Suspense>
        );
      
      case 'trades':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Trades />
          </Suspense>
        );
      
      case 'strategies':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Strategies />
          </Suspense>
        );
      
      case 'assets':
        return (
          <Suspense fallback={<ViewLoader />}>
            <Assets />
          </Suspense>
        );
      
      case 'alerts':
        return (
          <Suspense fallback={<ViewLoader />}>
            <AlertsView
              alerts={alerts}
              triggeredAlerts={triggeredAlerts}
              onCreateAlert={handleCreateAlert}
              onDeleteAlert={handleDeleteAlert}
              onRefresh={() => void fetchAlerts()}
            />
          </Suspense>
        );
      
      default:
        return (
          <Suspense fallback={<ViewLoader />}>
            <Overview />
          </Suspense>
        );
    }
  };

  // ---------------------------------------------------------------------------
  // LOADING SCREEN
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // MAIN RENDER
  // ---------------------------------------------------------------------------

  return (
    <div className="h-screen w-screen bg-[#0B0C0F] flex overflow-hidden">
      {/* Grain Overlay */}
      <div className="grain-overlay" />

      {/* Sidebar */}
      <Sidebar activeView={activeView} onViewChange={handleViewChange} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <TopBar
          onExport={handleExport}
          onOpenProfile={handleOpenProfile}
          onOpenSettings={handleOpenSettings}
          onOpenAuditLogs={handleOpenAuditLogs}
          onSignOut={handleSignOut}
        />

        {/* View Content */}
        <main className="flex-1 overflow-auto">
          <div
            key={activeView}
            className="animate-in fade-in slide-in-from-bottom-2 duration-300 h-full"
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

      {/* Modals */}
      <SettingsModal open={isSettingsOpen} onOpenChange={setIsSettingsOpen} />
      <ProfileModal
        open={isProfileOpen}
        onOpenChange={setIsProfileOpen}
        onSignOut={handleSignOut}
      />
    </div>
  );
}

// =============================================================================
// ROOT APP COMPONENT
// =============================================================================

function App() {
  return (
    <ThemeProvider>
      <WebSocketProvider>
        <AppContent />
      </WebSocketProvider>
    </ThemeProvider>
  );
}

export default App;
