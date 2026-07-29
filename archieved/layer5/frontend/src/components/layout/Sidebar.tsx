import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import {
  LayoutDashboard,
  ShieldAlert,
  GitBranch,
  Brain,
  ListOrdered,
  Target,
  TrendingUp,
} from 'lucide-react';
import type { ViewType } from '@/types';

interface SidebarProps {
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
}

const navItems: { view: ViewType; label: string; icon: React.ElementType }[] = [
  { view: 'overview', label: 'Overview', icon: LayoutDashboard },
  { view: 'risk', label: 'Risk', icon: ShieldAlert },
  { view: 'regimes', label: 'Regimes', icon: GitBranch },
  { view: 'model', label: 'Model', icon: Brain },
  { view: 'trades', label: 'Trades', icon: ListOrdered },
  { view: 'strategies', label: 'Strategies', icon: Target },
  { view: 'assets', label: 'Assets', icon: TrendingUp },
];

export function Sidebar({ activeView, onViewChange }: SidebarProps) {
  const sidebarRef = useRef<HTMLDivElement>(null);
  const itemsRef = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    // Entrance animation
    const ctx = gsap.context(() => {
      gsap.fromTo(
        sidebarRef.current,
        { x: -16, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.35, ease: 'power2.out' }
      );

      gsap.fromTo(
        itemsRef.current.filter(Boolean),
        { x: -12, opacity: 0 },
        {
          x: 0,
          opacity: 1,
          duration: 0.3,
          stagger: 0.05,
          ease: 'power2.out',
          delay: 0.15,
        }
      );
    });

    return () => ctx.revert();
  }, []);

  return (
    <aside
      ref={sidebarRef}
      className="w-16 lg:w-56 bg-[#14161C] border-r border-white/[0.06] flex flex-col h-full"
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-white/[0.06]">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-cyan-600 flex items-center justify-center">
          <span className="text-[#0B0C0F] font-bold text-sm">L5</span>
        </div>
        <span className="hidden lg:block ml-3 font-semibold text-[#F3F4F6]">
          Layer 5
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navItems.map((item, index) => {
          const Icon = item.icon;
          const isActive = activeView === item.view;

          return (
            <button
              key={item.view}
              ref={(el) => { itemsRef.current[index] = el; }}
              onClick={() => onViewChange(item.view)}
              className={`
                w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                transition-all duration-150 relative overflow-hidden group
                ${isActive
                  ? 'text-cyan-400 bg-cyan-500/10'
                  : 'text-[#A1A7B3] hover:text-[#F3F4F6] hover:bg-white/[0.04]'
                }
              `}
            >
              {/* Active indicator */}
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-cyan-400 rounded-r" />
              )}

              <Icon className={`w-5 h-5 ${isActive ? 'text-cyan-400' : ''}`} />
              
              <span className="hidden lg:block">{item.label}</span>

              {/* Keyboard shortcut */}
              <span className="hidden lg:block ml-auto text-xs text-[#6B7280] opacity-0 group-hover:opacity-100 transition-opacity">
                {index + 1}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Bottom status */}
      <div className="p-3 border-t border-white/[0.06]">
        <div className="flex items-center gap-2 px-2 py-2 rounded-lg bg-white/[0.02]">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="hidden lg:block text-xs text-[#A1A7B3]">System Online</span>
        </div>
      </div>
    </aside>
  );
}
