import { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useTheme } from '@/hooks/useTheme';
import {
  Moon,
  Sun,
  Bell,
  Wifi,
  Database,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface NotificationSettings {
  tradeAlerts: boolean;
  riskAlerts: boolean;
  modelDriftAlerts: boolean;
  emailNotifications: boolean;
  browserNotifications: boolean;
}

interface APIStatus {
  layer5: boolean;
  oanda: boolean;
  database: boolean;
  lastChecked: Date;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const ROOT_API_BASE_URL = API_BASE_URL.replace(/\/api\/v1$/, '') || '';

async function probeJson(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
    return response.ok;
  } catch {
    return false;
  }
}

const DEFAULT_NOTIFICATIONS: NotificationSettings = {
  tradeAlerts: true,
  riskAlerts: true,
  modelDriftAlerts: true,
  emailNotifications: false,
  browserNotifications: true,
};

export function SettingsModal({ open, onOpenChange }: SettingsModalProps) {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = useState('appearance');
  const [notifications, setNotifications] = useState<NotificationSettings>(DEFAULT_NOTIFICATIONS);
  const [apiStatus, setApiStatus] = useState<APIStatus>({
    layer5: true,
    oanda: false,
    database: true,
    lastChecked: new Date(),
  });
  const [isCheckingConnection, setIsCheckingConnection] = useState(false);

  // Load saved notification preferences
  useEffect(() => {
    const saved = localStorage.getItem('layer5-notifications');
    if (saved) {
      try {
        setNotifications({ ...DEFAULT_NOTIFICATIONS, ...JSON.parse(saved) });
      } catch {
        // Use defaults
      }
    }
  }, []);

  // Save notification preferences
  const saveNotifications = (newSettings: NotificationSettings) => {
    setNotifications(newSettings);
    localStorage.setItem('layer5-notifications', JSON.stringify(newSettings));
    toast.success('Notification preferences saved');
  };

  const handleCheckConnection = useCallback(async (showToast = true) => {
    setIsCheckingConnection(true);
    const [layer5Ok, oandaOk, databaseOk] = await Promise.all([
      probeJson(`${ROOT_API_BASE_URL}/health`),
      probeJson(`${API_BASE_URL}/streaming/health`),
      probeJson(`${API_BASE_URL}/kpi/`),
    ]);

    setApiStatus({
      layer5: layer5Ok,
      oanda: oandaOk,
      database: databaseOk,
      lastChecked: new Date(),
    });
    setIsCheckingConnection(false);
    if (showToast) {
      toast.success('Connection status updated');
    }
  }, []);

  useEffect(() => {
    if (open) {
      void handleCheckConnection(false);
    }
  }, [open, handleCheckConnection]);

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme);
    toast.success(`Theme set to ${newTheme}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[#14161C] border-white/[0.06] text-[#F3F4F6]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Settings
          </DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
          <TabsList className="bg-[#1E2129] border-white/[0.06]">
            <TabsTrigger value="appearance" className="data-[state=active]:bg-[#14161C]">
              <Sun className="w-4 h-4 mr-2" />
              Appearance
            </TabsTrigger>
            <TabsTrigger value="notifications" className="data-[state=active]:bg-[#14161C]">
              <Bell className="w-4 h-4 mr-2" />
              Notifications
            </TabsTrigger>
            <TabsTrigger value="connection" className="data-[state=active]:bg-[#14161C]">
              <Wifi className="w-4 h-4 mr-2" />
              Connection
            </TabsTrigger>
          </TabsList>

          {/* Appearance Tab */}
          <TabsContent value="appearance" className="space-y-4 mt-4">
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6] mb-3">Theme</h4>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    onClick={() => handleThemeChange('light')}
                    className={`
                      flex flex-col items-center gap-2 p-4 rounded-lg border transition-all
                      ${resolvedTheme === 'light' 
                        ? 'border-cyan-500 bg-cyan-500/10' 
                        : 'border-white/[0.06] hover:border-white/20 bg-[#1E2129]'}
                    `}
                  >
                    <Sun className="w-6 h-6 text-amber-400" />
                    <span className="text-sm text-[#F3F4F6]">Light</span>
                    {theme === 'light' && (
                      <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                    )}
                  </button>
                  <button
                    onClick={() => handleThemeChange('dark')}
                    className={`
                      flex flex-col items-center gap-2 p-4 rounded-lg border transition-all
                      ${resolvedTheme === 'dark' 
                        ? 'border-cyan-500 bg-cyan-500/10' 
                        : 'border-white/[0.06] hover:border-white/20 bg-[#1E2129]'}
                    `}
                  >
                    <Moon className="w-6 h-6 text-violet-400" />
                    <span className="text-sm text-[#F3F4F6]">Dark</span>
                    {theme === 'dark' && (
                      <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                    )}
                  </button>
                  <button
                    onClick={() => handleThemeChange('system')}
                    className={`
                      flex flex-col items-center gap-2 p-4 rounded-lg border transition-all
                      ${theme === 'system' 
                        ? 'border-cyan-500 bg-cyan-500/10' 
                        : 'border-white/[0.06] hover:border-white/20 bg-[#1E2129]'}
                    `}
                  >
                    <div className="flex -space-x-1">
                      <Sun className="w-4 h-4 text-amber-400" />
                      <Moon className="w-4 h-4 text-violet-400" />
                    </div>
                    <span className="text-sm text-[#F3F4F6]">System</span>
                    {theme === 'system' && (
                      <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                    )}
                  </button>
                </div>
              </div>

              <Separator className="bg-white/[0.06]" />

              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6] mb-3">Quick Toggle</h4>
                <Button
                  variant="outline"
                  onClick={toggleTheme}
                  className="border-white/[0.06] text-[#F3F4F6] hover:bg-white/[0.04]"
                >
                  {resolvedTheme === 'dark' ? (
                    <>
                      <Sun className="w-4 h-4 mr-2" />
                      Switch to Light Mode
                    </>
                  ) : (
                    <>
                      <Moon className="w-4 h-4 mr-2" />
                      Switch to Dark Mode
                    </>
                  )}
                </Button>
              </div>
            </div>
          </TabsContent>

          {/* Notifications Tab */}
          <TabsContent value="notifications" className="space-y-4 mt-4">
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6] mb-3">Alert Types</h4>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-full bg-emerald-500/10">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      </div>
                      <div>
                        <p className="text-sm text-[#F3F4F6]">Trade Alerts</p>
                        <p className="text-xs text-[#6B7280]">New trades, fills, and closures</p>
                      </div>
                    </div>
                    <Switch
                      checked={notifications.tradeAlerts}
                      onCheckedChange={(checked) => 
                        saveNotifications({ ...notifications, tradeAlerts: checked })
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-full bg-amber-500/10">
                        <Bell className="w-4 h-4 text-amber-400" />
                      </div>
                      <div>
                        <p className="text-sm text-[#F3F4F6]">Risk Alerts</p>
                        <p className="text-xs text-[#6B7280]">Drawdown, exposure warnings</p>
                      </div>
                    </div>
                    <Switch
                      checked={notifications.riskAlerts}
                      onCheckedChange={(checked) => 
                        saveNotifications({ ...notifications, riskAlerts: checked })
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-full bg-red-500/10">
                        <RefreshCw className="w-4 h-4 text-red-400" />
                      </div>
                      <div>
                        <p className="text-sm text-[#F3F4F6]">Model Drift Alerts</p>
                        <p className="text-xs text-[#6B7280]">Calibration and performance drift</p>
                      </div>
                    </div>
                    <Switch
                      checked={notifications.modelDriftAlerts}
                      onCheckedChange={(checked) => 
                        saveNotifications({ ...notifications, modelDriftAlerts: checked })
                      }
                    />
                  </div>
                </div>
              </div>

              <Separator className="bg-white/[0.06]" />

              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6] mb-3">Delivery Methods</h4>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div>
                      <p className="text-sm text-[#F3F4F6]">Browser Notifications</p>
                      <p className="text-xs text-[#6B7280]">Show desktop notifications</p>
                    </div>
                    <Switch
                      checked={notifications.browserNotifications}
                      onCheckedChange={(checked) => 
                        saveNotifications({ ...notifications, browserNotifications: checked })
                      }
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg opacity-50">
                    <div>
                      <p className="text-sm text-[#F3F4F6]">Email Notifications</p>
                      <p className="text-xs text-[#6B7280]">Send alerts to your email (Coming soon)</p>
                    </div>
                    <Switch
                      checked={notifications.emailNotifications}
                      onCheckedChange={(checked) => 
                        saveNotifications({ ...notifications, emailNotifications: checked })
                      }
                      disabled
                    />
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Connection Tab */}
          <TabsContent value="connection" className="space-y-4 mt-4">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium text-[#F3F4F6]">API Status</h4>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCheckConnection}
                  disabled={isCheckingConnection}
                  className="border-white/[0.06] text-[#F3F4F6] hover:bg-white/[0.04]"
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${isCheckingConnection ? 'animate-spin' : ''}`} />
                  {isCheckingConnection ? 'Checking...' : 'Check Now'}
                </Button>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                  <div className="flex items-center gap-3">
                    <Database className="w-4 h-4 text-[#6B7280]" />
                    <span className="text-sm text-[#F3F4F6]">Layer 5 API</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {apiStatus.layer5 ? (
                      <>
                        <span className="text-xs text-emerald-400">Connected</span>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      </>
                    ) : (
                      <>
                        <span className="text-xs text-red-400">Disconnected</span>
                        <XCircle className="w-4 h-4 text-red-400" />
                      </>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                  <div className="flex items-center gap-3">
                    <Wifi className="w-4 h-4 text-[#6B7280]" />
                    <span className="text-sm text-[#F3F4F6]">OANDA Stream</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {apiStatus.oanda ? (
                      <>
                        <span className="text-xs text-emerald-400">Connected</span>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      </>
                    ) : (
                      <>
                        <span className="text-xs text-red-400">Disconnected</span>
                        <XCircle className="w-4 h-4 text-red-400" />
                      </>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                  <div className="flex items-center gap-3">
                    <Database className="w-4 h-4 text-[#6B7280]" />
                    <span className="text-sm text-[#F3F4F6]">Database</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {apiStatus.database ? (
                      <>
                        <span className="text-xs text-emerald-400">Connected</span>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      </>
                    ) : (
                      <>
                        <span className="text-xs text-red-400">Disconnected</span>
                        <XCircle className="w-4 h-4 text-red-400" />
                      </>
                    )}
                  </div>
                </div>
              </div>

              <Separator className="bg-white/[0.06]" />

              <div className="text-xs text-[#6B7280]">
                Last checked: {apiStatus.lastChecked.toLocaleTimeString()}
              </div>

              <div className="bg-[#1E2129] rounded-lg p-4">
                <h5 className="text-sm font-medium text-[#F3F4F6] mb-2">API Configuration</h5>
                <div className="space-y-2 text-xs text-[#6B7280]">
                  <div className="flex justify-between">
                    <span>Base URL:</span>
                    <span className="text-[#A1A7B3]">{import.meta.env.VITE_API_BASE_URL || '/api/v1'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>WebSocket:</span>
                    <span className="text-[#A1A7B3]">{import.meta.env.VITE_WS_URL || 'Auto-detect'}</span>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
