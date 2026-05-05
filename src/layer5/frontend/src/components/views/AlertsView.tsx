import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  Bell, 
  Plus, 
  Trash2, 
  Pause, 
  Play, 
  CheckCircle2, 
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  RefreshCw
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AlertConfig, AlertType, AlertCondition } from '@/types';

interface AlertsViewProps {
  alerts: AlertConfig[];
  triggeredAlerts: AlertConfig[];
  onCreateAlert: (alert: Omit<AlertConfig, 'id' | 'status' | 'created_at'>) => void;
  onDeleteAlert: (alertId: string) => void;
  onRefresh: () => void;
}

const ALERT_TYPES: { value: AlertType; label: string }[] = [
  { value: 'price', label: 'Price' },
  { value: 'indicator', label: 'Indicator' },
  { value: 'volume', label: 'Volume' },
  { value: 'pattern', label: 'Pattern' },
];

const ALERT_CONDITIONS: { value: AlertCondition; label: string }[] = [
  { value: 'above', label: 'Above' },
  { value: 'below', label: 'Below' },
  { value: 'crosses_above', label: 'Crosses Above' },
  { value: 'crosses_below', label: 'Crosses Below' },
  { value: 'equals', label: 'Equals' },
];

export function AlertsView({
  alerts,
  triggeredAlerts,
  onCreateAlert,
  onDeleteAlert,
  onRefresh,
}: AlertsViewProps) {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newAlert, setNewAlert] = useState<Partial<AlertConfig>>({
    type: 'price',
    condition: 'above',
    timeframe: '1h',
  });

  const activeAlerts = alerts.filter(a => a.status === 'active');
  const pausedAlerts = alerts.filter(a => a.status === 'paused');

  const handleCreateAlert = () => {
    if (newAlert.name && newAlert.symbol && newAlert.value !== undefined) {
      onCreateAlert({
        name: newAlert.name,
        type: newAlert.type || 'price',
        symbol: newAlert.symbol,
        condition: newAlert.condition || 'above',
        value: newAlert.value,
        timeframe: newAlert.timeframe || '1h',
        message: newAlert.message,
      });
      setIsCreateOpen(false);
      setNewAlert({ type: 'price', condition: 'above', timeframe: '1h' });
    }
  };

  const getConditionIcon = (condition: AlertCondition) => {
    if (condition.includes('above')) return <TrendingUp className="h-4 w-4" />;
    if (condition.includes('below')) return <TrendingDown className="h-4 w-4" />;
    return <Bell className="h-4 w-4" />;
  };

  const getStatusBadge = (status: string) => {
    const styles = {
      active: 'bg-green-500/10 text-green-500 border-green-500/20',
      triggered: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
      paused: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
      expired: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
    };
    return styles[status as keyof typeof styles] || styles.expired;
  };

  const renderAlertCard = (alert: AlertConfig, showActions = true) => (
    <div
      key={alert.id}
      className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className={cn(
          "p-2 rounded-full",
          alert.status === 'triggered' ? "bg-blue-500/10" : "bg-primary/10"
        )}>
          {getConditionIcon(alert.condition)}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium">{alert.name}</span>
            <Badge variant="outline" className={cn("text-xs", getStatusBadge(alert.status))}>
              {alert.status}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {alert.symbol} {alert.condition.replace('_', ' ')} {alert.value}
            {alert.timeframe && ` · ${alert.timeframe}`}
          </p>
          {alert.message && (
            <p className="text-xs text-muted-foreground mt-1">{alert.message}</p>
          )}
          {alert.triggered_at && (
            <p className="text-xs text-blue-500 mt-1">
              Triggered at {new Date(alert.triggered_at).toLocaleString()}
              {alert.triggered_price && ` (Price: ${alert.triggered_price})`}
            </p>
          )}
        </div>
      </div>

      {showActions && (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onDeleteAlert(alert.id!)}
          >
            <Trash2 className="h-4 w-4 text-muted-foreground" />
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Alerts</h2>
          <p className="text-muted-foreground">Manage price and indicator alerts</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-2" />
                New Alert
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Create New Alert</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Alert Name</Label>
                  <Input
                    placeholder="e.g., EURUSD Support Break"
                    value={newAlert.name || ''}
                    onChange={(e) => setNewAlert({ ...newAlert, name: e.target.value })}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Symbol</Label>
                    <Input
                      placeholder="EUR_USD"
                      value={newAlert.symbol || ''}
                      onChange={(e) => setNewAlert({ ...newAlert, symbol: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Type</Label>
                    <Select
                      value={newAlert.type}
                      onValueChange={(v) => setNewAlert({ ...newAlert, type: v as AlertType })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ALERT_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Condition</Label>
                    <Select
                      value={newAlert.condition}
                      onValueChange={(v) => setNewAlert({ ...newAlert, condition: v as AlertCondition })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ALERT_CONDITIONS.map((c) => (
                          <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Value</Label>
                    <Input
                      type="number"
                      step="0.0001"
                      value={newAlert.value || ''}
                      onChange={(e) => setNewAlert({ ...newAlert, value: parseFloat(e.target.value) })}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Timeframe</Label>
                  <Select
                    value={newAlert.timeframe}
                    onValueChange={(v) => setNewAlert({ ...newAlert, timeframe: v })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1m">1 Minute</SelectItem>
                      <SelectItem value="5m">5 Minutes</SelectItem>
                      <SelectItem value="15m">15 Minutes</SelectItem>
                      <SelectItem value="1h">1 Hour</SelectItem>
                      <SelectItem value="4h">4 Hours</SelectItem>
                      <SelectItem value="1d">1 Day</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Message (Optional)</Label>
                  <Input
                    placeholder="Custom alert message..."
                    value={newAlert.message || ''}
                    onChange={(e) => setNewAlert({ ...newAlert, message: e.target.value })}
                  />
                </div>

                <Button className="w-full" onClick={handleCreateAlert}>
                  Create Alert
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Active</p>
                <p className="text-2xl font-bold">{activeAlerts.length}</p>
              </div>
              <div className="p-2 bg-green-500/10 rounded-full">
                <Bell className="h-5 w-5 text-green-500" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Triggered (24h)</p>
                <p className="text-2xl font-bold">{triggeredAlerts.length}</p>
              </div>
              <div className="p-2 bg-blue-500/10 rounded-full">
                <CheckCircle2 className="h-5 w-5 text-blue-500" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Paused</p>
                <p className="text-2xl font-bold">{pausedAlerts.length}</p>
              </div>
              <div className="p-2 bg-amber-500/10 rounded-full">
                <Pause className="h-5 w-5 text-amber-500" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total</p>
                <p className="text-2xl font-bold">{alerts.length}</p>
              </div>
              <div className="p-2 bg-primary/10 rounded-full">
                <AlertTriangle className="h-5 w-5 text-primary" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="active" className="w-full">
        <TabsList>
          <TabsTrigger value="active">
            Active
            {activeAlerts.length > 0 && (
              <Badge variant="secondary" className="ml-2">{activeAlerts.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="triggered">
            Triggered
            {triggeredAlerts.length > 0 && (
              <Badge variant="secondary" className="ml-2">{triggeredAlerts.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="all">All Alerts</TabsTrigger>
        </TabsList>

        <TabsContent value="active">
          <Card>
            <CardContent className="p-4">
              <ScrollArea className="h-[400px]">
                <div className="space-y-2">
                  {activeAlerts.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <Bell className="h-12 w-12 mx-auto mb-2 opacity-50" />
                      <p>No active alerts</p>
                      <p className="text-sm">Create an alert to get notified of price movements</p>
                    </div>
                  ) : (
                    activeAlerts.map((alert) => renderAlertCard(alert))
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="triggered">
          <Card>
            <CardContent className="p-4">
              <ScrollArea className="h-[400px]">
                <div className="space-y-2">
                  {triggeredAlerts.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <CheckCircle2 className="h-12 w-12 mx-auto mb-2 opacity-50" />
                      <p>No triggered alerts in the last 24 hours</p>
                    </div>
                  ) : (
                    triggeredAlerts.map((alert) => renderAlertCard(alert, false))
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="all">
          <Card>
            <CardContent className="p-4">
              <ScrollArea className="h-[400px]">
                <div className="space-y-2">
                  {alerts.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <Bell className="h-12 w-12 mx-auto mb-2 opacity-50" />
                      <p>No alerts configured</p>
                    </div>
                  ) : (
                    alerts.map((alert) => renderAlertCard(alert))
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
