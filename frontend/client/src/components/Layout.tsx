import { Link, useLocation } from "wouter";
import { cn } from "@/lib/utils";
import { 
  LayoutDashboard, 
  FileText, 
  Network, 
  Settings, 
  ShieldCheck,
  Search
} from "lucide-react";

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const [location] = useLocation();

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", path: "/" },
    { icon: FileText, label: "Document Review", path: "/review" },
    { icon: Network, label: "Citation Network", path: "/network" },
    { icon: Search, label: "Research", path: "/research" },
  ];

  return (
    <div className="min-h-screen bg-background flex font-sans">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border bg-sidebar flex flex-col fixed h-full z-10">
        <div className="p-6 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-primary text-primary-foreground flex items-center justify-center font-bold text-lg">
              M
            </div>
            <span className="font-bold text-xl tracking-tight text-foreground">MikeCheck</span>
          </div>
          <div className="mt-2 text-xs text-muted-foreground uppercase tracking-wider font-medium">
            Legal Verification
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const isActive = location === item.path;
            return (
              <Link key={item.path} href={item.path}>
                <div
                  className={cn(
                    "flex items-center gap-3 px-4 py-3 text-sm font-medium transition-colors cursor-pointer group",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <item.icon className={cn("w-5 h-5", isActive ? "text-primary-foreground" : "text-muted-foreground group-hover:text-accent-foreground")} />
                  {item.label}
                </div>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border">
          <Link href="/settings">
            <div className="flex items-center gap-3 px-4 py-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
              <Settings className="w-5 h-5" />
              Settings
            </div>
          </Link>
          <div className="mt-4 px-4 py-3 bg-accent/50 text-xs text-muted-foreground">
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck className="w-3 h-3 text-green-600" />
              <span className="font-semibold">System Operational</span>
            </div>
            v1.0.0 • Swiss Edition
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 ml-64 min-h-screen flex flex-col">
        {children}
      </main>
    </div>
  );
}
