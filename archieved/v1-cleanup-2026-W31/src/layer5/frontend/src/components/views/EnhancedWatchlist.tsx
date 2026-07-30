import { useState, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { 
  Search, 
  Star, 
  TrendingUp, 
  TrendingDown, 
  MoreHorizontal,
  Bell,
  BarChart3,
  ArrowUpDown
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  change24hPct: number;
  volume: number;
  high24h: number;
  low24h: number;
  regime: string;
  atr: number;
  isFavorite?: boolean;
}

interface EnhancedWatchlistProps {
  items: WatchlistItem[];
  onSymbolSelect?: (symbol: string) => void;
  onAddAlert?: (symbol: string) => void;
  onToggleFavorite?: (symbol: string) => void;
  selectedSymbol?: string;
  className?: string;
}

type SortField = 'symbol' | 'price' | 'change24hPct' | 'volume' | 'atr';
type SortDirection = 'asc' | 'desc';

export function EnhancedWatchlist({
  items,
  onSymbolSelect,
  onAddAlert,
  onToggleFavorite,
  selectedSymbol,
  className,
}: EnhancedWatchlistProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<SortField>('symbol');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const filteredAndSortedItems = useMemo(() => {
    let result = [...items];

    // Filter by search
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        item =>
          item.symbol.toLowerCase().includes(query) ||
          item.name.toLowerCase().includes(query)
      );
    }

    // Filter favorites
    if (showFavoritesOnly) {
      result = result.filter(item => item.isFavorite);
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'symbol':
          comparison = a.symbol.localeCompare(b.symbol);
          break;
        case 'price':
          comparison = a.price - b.price;
          break;
        case 'change24hPct':
          comparison = a.change24hPct - b.change24hPct;
          break;
        case 'volume':
          comparison = a.volume - b.volume;
          break;
        case 'atr':
          comparison = a.atr - b.atr;
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [items, searchQuery, showFavoritesOnly, sortField, sortDirection]);

  const getRegimeColor = (regime: string) => {
    if (regime.includes('Trending')) return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
    if (regime.includes('Ranging')) return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
    return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
  };

  return (
    <div className={cn("flex flex-col h-full bg-card rounded-lg border border-border", className)}>
      {/* Header */}
      <div className="p-3 border-b border-border space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Watchlist</h3>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className={cn("h-7 w-7", showFavoritesOnly && "text-yellow-500")}
              onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            >
              <Star className={cn("h-4 w-4", showFavoritesOnly && "fill-current")} />
            </Button>
          </div>
        </div>

        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search symbols..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-9"
          />
        </div>
      </div>

      {/* Table */}
      <ScrollArea className="flex-1">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8"></TableHead>
              <TableHead 
                className="cursor-pointer"
                onClick={() => handleSort('symbol')}
              >
                <span className="flex items-center gap-1">
                  Symbol
                  {sortField === 'symbol' && (
                    <ArrowUpDown className="h-3 w-3" />
                  )}
                </span>
              </TableHead>
              <TableHead 
                className="cursor-pointer text-right"
                onClick={() => handleSort('price')}
              >
                <span className="flex items-center justify-end gap-1">
                  Price
                  {sortField === 'price' && (
                    <ArrowUpDown className="h-3 w-3" />
                  )}
                </span>
              </TableHead>
              <TableHead 
                className="cursor-pointer text-right"
                onClick={() => handleSort('change24hPct')}
              >
                <span className="flex items-center justify-end gap-1">
                  24h %
                  {sortField === 'change24hPct' && (
                    <ArrowUpDown className="h-3 w-3" />
                  )}
                </span>
              </TableHead>
              <TableHead className="w-8"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredAndSortedItems.map((item) => (
              <TableRow
                key={item.symbol}
                className={cn(
                  "cursor-pointer",
                  selectedSymbol === item.symbol && "bg-accent"
                )}
                onClick={() => onSymbolSelect?.(item.symbol)}
              >
                <TableCell className="p-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleFavorite?.(item.symbol);
                    }}
                  >
                    <Star 
                      className={cn(
                        "h-3.5 w-3.5",
                        item.isFavorite && "fill-yellow-500 text-yellow-500"
                      )} 
                    />
                  </Button>
                </TableCell>
                <TableCell className="p-2">
                  <div>
                    <span className="font-medium">{item.symbol}</span>
                    <div className="flex items-center gap-1 mt-0.5">
                      <Badge 
                        variant="outline" 
                        className={cn("text-[10px] px-1 py-0 h-4", getRegimeColor(item.regime))}
                      >
                        {item.regime.split('_')[0]}
                      </Badge>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="p-2 text-right">
                  <span className="font-mono">{item.price.toFixed(5)}</span>
                </TableCell>
                <TableCell className="p-2 text-right">
                  <span
                    className={cn(
                      "font-mono flex items-center justify-end gap-1",
                      item.change24hPct >= 0 ? "text-green-500" : "text-red-500"
                    )}
                  >
                    {item.change24hPct >= 0 ? (
                      <TrendingUp className="h-3 w-3" />
                    ) : (
                      <TrendingDown className="h-3 w-3" />
                    )}
                    {Math.abs(item.change24hPct).toFixed(2)}%
                  </span>
                </TableCell>
                <TableCell className="p-2">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-6 w-6"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => onSymbolSelect?.(item.symbol)}>
                        <BarChart3 className="mr-2 h-4 w-4" />
                        Open Chart
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onAddAlert?.(item.symbol)}>
                        <Bell className="mr-2 h-4 w-4" />
                        Set Alert
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {filteredAndSortedItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Search className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-sm">No symbols found</p>
          </div>
        )}
      </ScrollArea>

      {/* Footer */}
      <div className="p-2 border-t border-border text-xs text-muted-foreground text-center">
        {filteredAndSortedItems.length} of {items.length} symbols
      </div>
    </div>
  );
}
