import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { toast } from 'sonner';
import {
  User,
  Mail,
  Shield,
  Activity,
  Clock,
  Settings,
  LogOut,
  Edit3,
  CheckCircle2,
} from 'lucide-react';

interface ProfileModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSignOut?: () => void;
}

interface UserProfile {
  name: string;
  email: string;
  role: string;
  lastLogin: Date;
  joinedDate: Date;
  avatar?: string;
}

interface ActivityItem {
  id: string;
  type: 'login' | 'trade' | 'alert' | 'settings';
  description: string;
  timestamp: Date;
}

const DEFAULT_PROFILE: UserProfile = {
  name: 'Trader User',
  email: 'trader@layer5.local',
  role: 'Administrator',
  lastLogin: new Date(),
  joinedDate: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000), // 90 days ago
};

const MOCK_ACTIVITIES: ActivityItem[] = [
  {
    id: '1',
    type: 'login',
    description: 'Logged in from Chrome on macOS',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
  },
  {
    id: '2',
    type: 'trade',
    description: 'Executed EUR_USD long position',
    timestamp: new Date(Date.now() - 4 * 60 * 60 * 1000),
  },
  {
    id: '3',
    type: 'alert',
    description: 'Created price alert for GBP_USD',
    timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000),
  },
  {
    id: '4',
    type: 'settings',
    description: 'Updated notification preferences',
    timestamp: new Date(Date.now() - 48 * 60 * 60 * 1000),
  },
];

export function ProfileModal({ open, onOpenChange, onSignOut }: ProfileModalProps) {
  const [activeTab, setActiveTab] = useState('profile');
  const [isEditing, setIsEditing] = useState(false);
  const [profile, setProfile] = useState<UserProfile>(DEFAULT_PROFILE);
  const [editedProfile, setEditedProfile] = useState<UserProfile>(DEFAULT_PROFILE);

  // Load profile from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('layer5-profile');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setProfile({
          ...DEFAULT_PROFILE,
          ...parsed,
          lastLogin: new Date(parsed.lastLogin || Date.now()),
          joinedDate: new Date(parsed.joinedDate || Date.now()),
        });
      } catch {
        // Use defaults
      }
    }
  }, []);

  const handleSaveProfile = () => {
    setProfile(editedProfile);
    localStorage.setItem('layer5-profile', JSON.stringify(editedProfile));
    setIsEditing(false);
    toast.success('Profile updated successfully');
  };

  const handleCancelEdit = () => {
    setEditedProfile(profile);
    setIsEditing(false);
  };

  const getActivityIcon = (type: ActivityItem['type']) => {
    switch (type) {
      case 'login':
        return <Shield className="w-4 h-4 text-cyan-400" />;
      case 'trade':
        return <Activity className="w-4 h-4 text-emerald-400" />;
      case 'alert':
        return <CheckCircle2 className="w-4 h-4 text-amber-400" />;
      case 'settings':
        return <Settings className="w-4 h-4 text-violet-400" />;
    }
  };

  const formatTimeAgo = (date: Date) => {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'Just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[#14161C] border-white/[0.06] text-[#F3F4F6]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="w-5 h-5" />
            Profile
          </DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
          <TabsList className="bg-[#1E2129] border-white/[0.06]">
            <TabsTrigger value="profile" className="data-[state=active]:bg-[#14161C]">
              <User className="w-4 h-4 mr-2" />
              Profile
            </TabsTrigger>
            <TabsTrigger value="activity" className="data-[state=active]:bg-[#14161C]">
              <Activity className="w-4 h-4 mr-2" />
              Activity
            </TabsTrigger>
            <TabsTrigger value="security" className="data-[state=active]:bg-[#14161C]">
              <Shield className="w-4 h-4 mr-2" />
              Security
            </TabsTrigger>
          </TabsList>

          {/* Profile Tab */}
          <TabsContent value="profile" className="space-y-4 mt-4">
            <div className="flex items-center gap-4">
              <Avatar className="w-20 h-20 border-2 border-cyan-500/30">
                <AvatarImage src={profile.avatar} />
                <AvatarFallback className="bg-gradient-to-br from-cyan-500 to-violet-500 text-white text-xl">
                  {profile.name.split(' ').map(n => n[0]).join('').toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div>
                <h3 className="text-lg font-semibold text-[#F3F4F6]">{profile.name}</h3>
                <p className="text-sm text-[#6B7280]">{profile.email}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400">
                    {profile.role}
                  </span>
                  <span className="text-xs text-[#6B7280]">
                    Member since {profile.joinedDate.toLocaleDateString()}
                  </span>
                </div>
              </div>
            </div>

            <Separator className="bg-white/[0.06]" />

            {isEditing ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Display Name</Label>
                    <Input
                      id="name"
                      value={editedProfile.name}
                      onChange={(e) => setEditedProfile({ ...editedProfile, name: e.target.value })}
                      className="bg-[#1E2129] border-white/[0.06] text-[#F3F4F6]"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={editedProfile.email}
                      onChange={(e) => setEditedProfile({ ...editedProfile, email: e.target.value })}
                      className="bg-[#1E2129] border-white/[0.06] text-[#F3F4F6]"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={handleSaveProfile}
                    className="bg-cyan-500 hover:bg-cyan-600"
                  >
                    <CheckCircle2 className="w-4 h-4 mr-2" />
                    Save Changes
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleCancelEdit}
                    className="border-white/[0.06] text-[#F3F4F6] hover:bg-white/[0.04]"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-2 text-[#6B7280] mb-1">
                      <User className="w-4 h-4" />
                      <span className="text-xs">Display Name</span>
                    </div>
                    <p className="text-sm text-[#F3F4F6]">{profile.name}</p>
                  </div>
                  <div className="p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-2 text-[#6B7280] mb-1">
                      <Mail className="w-4 h-4" />
                      <span className="text-xs">Email</span>
                    </div>
                    <p className="text-sm text-[#F3F4F6]">{profile.email}</p>
                  </div>
                  <div className="p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-2 text-[#6B7280] mb-1">
                      <Shield className="w-4 h-4" />
                      <span className="text-xs">Role</span>
                    </div>
                    <p className="text-sm text-[#F3F4F6]">{profile.role}</p>
                  </div>
                  <div className="p-3 bg-[#1E2129] rounded-lg">
                    <div className="flex items-center gap-2 text-[#6B7280] mb-1">
                      <Clock className="w-4 h-4" />
                      <span className="text-xs">Last Login</span>
                    </div>
                    <p className="text-sm text-[#F3F4F6]">
                      {profile.lastLogin.toLocaleString()}
                    </p>
                  </div>
                </div>

                <Button
                  variant="outline"
                  onClick={() => {
                    setEditedProfile(profile);
                    setIsEditing(true);
                  }}
                  className="border-white/[0.06] text-[#F3F4F6] hover:bg-white/[0.04]"
                >
                  <Edit3 className="w-4 h-4 mr-2" />
                  Edit Profile
                </Button>
              </div>
            )}

            <Separator className="bg-white/[0.06]" />

            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6]">Session</h4>
                <p className="text-xs text-[#6B7280]">Manage your current session</p>
              </div>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  onSignOut?.();
                  onOpenChange(false);
                }}
              >
                <LogOut className="w-4 h-4 mr-2" />
                Sign Out
              </Button>
            </div>
          </TabsContent>

          {/* Activity Tab */}
          <TabsContent value="activity" className="space-y-4 mt-4">
            <h4 className="text-sm font-medium text-[#F3F4F6]">Recent Activity</h4>
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {MOCK_ACTIVITIES.map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-center gap-3 p-3 bg-[#1E2129] rounded-lg"
                >
                  <div className="p-2 rounded-full bg-[#14161C]">
                    {getActivityIcon(activity.type)}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-[#F3F4F6]">{activity.description}</p>
                    <p className="text-xs text-[#6B7280]">{formatTimeAgo(activity.timestamp)}</p>
                  </div>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* Security Tab */}
          <TabsContent value="security" className="space-y-4 mt-4">
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6] mb-3">Security Settings</h4>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div>
                      <p className="text-sm text-[#F3F4F6]">Two-Factor Authentication</p>
                      <p className="text-xs text-[#6B7280]">Add an extra layer of security</p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled
                      className="border-white/[0.06] text-[#6B7280]"
                    >
                      Coming Soon
                    </Button>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div>
                      <p className="text-sm text-[#F3F4F6]">API Keys</p>
                      <p className="text-xs text-[#6B7280]">Manage your API access tokens</p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled
                      className="border-white/[0.06] text-[#6B7280]"
                    >
                      Coming Soon
                    </Button>
                  </div>

                  <div className="flex items-center justify-between p-3 bg-[#1E2129] rounded-lg">
                    <div>
                      <p className="text-sm text-[#F3F4F6]">Session Timeout</p>
                      <p className="text-xs text-[#6B7280]">Auto-logout after inactivity</p>
                    </div>
                    <span className="text-sm text-[#A1A7B3]">30 minutes</span>
                  </div>
                </div>
              </div>

              <Separator className="bg-white/[0.06]" />

              <div>
                <h4 className="text-sm font-medium text-[#F3F4F6] mb-3">Active Sessions</h4>
                <div className="p-3 bg-[#1E2129] rounded-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-full bg-emerald-500/10">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      </div>
                      <div>
                        <p className="text-sm text-[#F3F4F6]">Current Session</p>
                        <p className="text-xs text-[#6B7280]">Chrome on macOS · IP: 192.168.1.x</p>
                      </div>
                    </div>
                    <span className="text-xs text-emerald-400">Active</span>
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
