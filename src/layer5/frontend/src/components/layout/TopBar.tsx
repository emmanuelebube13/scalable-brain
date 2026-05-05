import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { Search, Bell, Download, User, Clock, Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { format } from 'date-fns';
import { useTheme } from '@/hooks/useTheme';

interface TopBarProps {
  onExport?: () => void;
  onOpenProfile?: () => void;
  onOpenSettings?: () => void;
  onOpenAuditLogs?: () => void;
  onSignOut?: () => void;
}

export function TopBar({
  onExport,
  onOpenProfile,
  onOpenSettings,
  onOpenAuditLogs,
  onSignOut,
}: TopBarProps) {
  const topBarRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [searchQuery, setSearchQuery] = useState('');
  const { resolvedTheme, toggleTheme } = useTheme();

  useEffect(() => {
    // Entrance animation
    gsap.fromTo(
      topBarRef.current,
      { y: -12, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.35, ease: 'power2.out' }
    );

    // Update clock
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  return (
    <header
      ref={topBarRef}
      className="h-14 bg-[#14161C] border-b border-white/[0.06] flex items-center justify-between px-4"
    >
      {/* Left: Breadcrumbs / Title */}
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold text-[#F3F4F6]">
          Live Telemetry
        </h1>
        <span className="text-[#6B7280]">|</span>
        <div className="flex items-center gap-2 text-sm text-[#A1A7B3]">
          <Clock className="w-4 h-4" />
          <span className="font-mono">
            {format(currentTime, 'yyyy-MM-dd HH:mm:ss')} {Intl.DateTimeFormat().resolvedOptions().timeZone}
          </span>
        </div>
      </div>

      {/* Center: Search */}
      <div className="flex-1 max-w-md mx-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6B7280]" />
          <Input
            type="text"
            placeholder="Search assets, strategies, trade IDs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 bg-[#1E2129] border-white/[0.06] text-[#F3F4F6] placeholder:text-[#6B7280] h-9"
          />
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          title={resolvedTheme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="text-[#A1A7B3] hover:text-[#F3F4F6] hover:bg-white/[0.04]"
        >
          {resolvedTheme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>

        {/* Export Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onExport}
          className="text-[#A1A7B3] hover:text-[#F3F4F6] hover:bg-white/[0.04]"
        >
          <Download className="w-4 h-4 mr-2" />
          Export
        </Button>

        {/* Notifications */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="relative text-[#A1A7B3] hover:text-[#F3F4F6] hover:bg-white/[0.04]"
            >
              <Bell className="w-4 h-4" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-amber-500 rounded-full" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 bg-[#14161C] border-white/[0.06]">
            <div className="px-3 py-2 text-sm font-medium text-[#F3F4F6]">
              Notifications
            </div>
            <DropdownMenuSeparator className="bg-white/[0.06]" />
            <DropdownMenuItem className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]">
              <span className="w-2 h-2 bg-amber-500 rounded-full mr-2" />
              Drift alert: Approval rate down 15%
            </DropdownMenuItem>
            <DropdownMenuItem className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]">
              <span className="w-2 h-2 bg-red-500 rounded-full mr-2" />
              Correlation block: 3 EUR trades
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={onOpenAuditLogs}
              className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]"
            >
              <span className="w-2 h-2 bg-emerald-500 rounded-full mr-2" />
              New model deployed: v2.1.4
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="text-[#A1A7B3] hover:text-[#F3F4F6] hover:bg-white/[0.04]"
            >
              <User className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="bg-[#14161C] border-white/[0.06]">
            <DropdownMenuItem onClick={onOpenProfile} className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]">
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onOpenAuditLogs} className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]">
              Audit Logs
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onOpenSettings} className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]">
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-white/[0.06]" />
            <DropdownMenuItem onClick={onSignOut} className="text-[#A1A7B3] focus:bg-white/[0.04] focus:text-[#F3F4F6]">
              Sign Out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
