import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Plus, X, TrendingUp, Activity, BarChart3, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Indicator {
  id: string;
  name: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume';
  defaultParams: Record<string, number>;
}

interface ActiveIndicator extends Indicator {
  instanceId: string;
  params: Record<string, number>;
}

interface IndicatorPanelProps {
  activeIndicators: ActiveIndicator[];
  onAddIndicator: (indicator: Indicator, params: Record<string, number>) => void;
  onRemoveIndicator: (instanceId: string) => void;
  onUpdateParams: (instanceId: string, params: Record<string, number>) => void;
  className?: string;
}

const AVAILABLE_INDICATORS: Indicator[] = [
  // Trend
  { id: 'sma', name: 'Simple Moving Average', category: 'trend', defaultParams: { period: 20 } },
  { id: 'ema', name: 'Exponential Moving Average', category: 'trend', defaultParams: { period: 20 } },
  { id: 'wma', name: 'Weighted Moving Average', category: 'trend', defaultParams: { period: 20 } },
  { id: 'macd', name: 'MACD', category: 'trend', defaultParams: { fast: 12, slow: 26, signal: 9 } },
  { id: 'adx', name: 'Average Directional Index', category: 'trend', defaultParams: { period: 14 } },
  
  // Momentum
  { id: 'rsi', name: 'RSI', category: 'momentum', defaultParams: { period: 14, overbought: 70, oversold: 30 } },
  { id: 'stochastic', name: 'Stochastic Oscillator', category: 'momentum', defaultParams: { kPeriod: 14, dPeriod: 3 } },
  
  // Volatility
  { id: 'bollinger', name: 'Bollinger Bands', category: 'volatility', defaultParams: { period: 20, stdDev: 2 } },
  { id: 'atr', name: 'Average True Range', category: 'volatility', defaultParams: { period: 14 } },
  
  // Volume
  { id: 'obv', name: 'On-Balance Volume', category: 'volume', defaultParams: {} },
];

const CATEGORY_ICONS = {
  trend: TrendingUp,
  momentum: Activity,
  volatility: BarChart3,
  volume: Layers,
};

const CATEGORY_COLORS = {
  trend: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  momentum: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  volatility: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
  volume: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
};

export function IndicatorPanel({
  activeIndicators,
  onAddIndicator,
  onRemoveIndicator,
  onUpdateParams,
  className,
}: IndicatorPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndicator, setSelectedIndicator] = useState<Indicator | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, number>>({});

  const handleSelectIndicator = (indicator: Indicator) => {
    setSelectedIndicator(indicator);
    setParamValues({ ...indicator.defaultParams });
  };

  const handleAddIndicator = () => {
    if (selectedIndicator) {
      onAddIndicator(selectedIndicator, paramValues);
      setSelectedIndicator(null);
      setParamValues({});
      setIsOpen(false);
    }
  };

  const handleParamChange = (key: string, value: number) => {
    setParamValues(prev => ({ ...prev, [key]: value }));
  };

  const groupedIndicators = AVAILABLE_INDICATORS.reduce((acc, ind) => {
    if (!acc[ind.category]) acc[ind.category] = [];
    acc[ind.category].push(ind);
    return acc;
  }, {} as Record<string, Indicator[]>);

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Indicators</h3>
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="h-7 gap-1">
              <Plus className="h-3.5 w-3.5" />
              Add
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md max-h-[80vh]">
            <DialogHeader>
              <DialogTitle>Add Indicator</DialogTitle>
            </DialogHeader>
            
            {!selectedIndicator ? (
              <ScrollArea className="h-[500px]">
                <Accordion type="single" collapsible className="w-full">
                  {Object.entries(groupedIndicators).map(([category, indicators]) => {
                    const Icon = CATEGORY_ICONS[category as keyof typeof CATEGORY_ICONS];
                    return (
                      <AccordionItem key={category} value={category}>
                        <AccordionTrigger className="text-sm capitalize">
                          <span className="flex items-center gap-2">
                            <Icon className="h-4 w-4" />
                            {category}
                          </span>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="flex flex-col gap-1">
                            {indicators.map(ind => (
                              <Button
                                key={ind.id}
                                variant="ghost"
                                className="justify-start text-sm h-8"
                                onClick={() => handleSelectIndicator(ind)}
                              >
                                {ind.name}
                              </Button>
                            ))}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    );
                  })}
                </Accordion>
              </ScrollArea>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium">{selectedIndicator.name}</h4>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedIndicator(null)}
                  >
                    Back
                  </Button>
                </div>
                
                <div className="space-y-4">
                  {Object.entries(selectedIndicator.defaultParams).map(([key, defaultValue]) => (
                    <div key={key} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-sm capitalize">{key}</Label>
                        <span className="text-sm text-muted-foreground">
                          {paramValues[key] || defaultValue}
                        </span>
                      </div>
                      <Slider
                        value={[paramValues[key] || defaultValue]}
                        onValueChange={([v]) => handleParamChange(key, v)}
                        min={key.includes('period') ? 2 : 0}
                        max={key.includes('period') ? 200 : 100}
                        step={key.includes('period') ? 1 : 0.1}
                      />
                    </div>
                  ))}
                </div>
                
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" onClick={() => setSelectedIndicator(null)}>
                    Cancel
                  </Button>
                  <Button className="flex-1" onClick={handleAddIndicator}>
                    Add Indicator
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>

      {/* Active Indicators List */}
      <div className="space-y-2">
        {activeIndicators.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            No active indicators
          </p>
        ) : (
          activeIndicators.map(ind => {
            const Icon = CATEGORY_ICONS[ind.category];
            return (
              <div
                key={ind.instanceId}
                className="flex items-center justify-between p-2 rounded-md border bg-card hover:bg-accent/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">{ind.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {Object.entries(ind.params).map(([k, v]) => `${k}: ${v}`).join(', ')}
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={() => onRemoveIndicator(ind.instanceId)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
