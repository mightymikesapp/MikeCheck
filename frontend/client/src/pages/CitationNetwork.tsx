import { useState } from "react";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  Search, 
  ZoomIn, 
  ZoomOut, 
  Maximize, 
  Filter,
  Download,
  Share2
} from "lucide-react";

export default function CitationNetwork() {
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <Layout>
      <div className="h-screen flex flex-col bg-background overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-border bg-background flex items-center justify-between px-6 shrink-0 z-20">
          <div className="flex items-center gap-4 flex-1">
            <h1 className="text-lg font-bold text-foreground">Citation Network</h1>
            <div className="h-6 w-px bg-border" />
            <div className="relative max-w-md w-full">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input 
                placeholder="Search cases (e.g., Roe v. Wade)..." 
                className="pl-9 bg-accent/50 border-transparent focus:bg-background focus:border-primary"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm">
              <Filter className="w-4 h-4 mr-2" /> Filters
            </Button>
            <Button variant="outline" size="sm">
              <Download className="w-4 h-4 mr-2" /> Export
            </Button>
            <Button variant="default" size="sm">
              <Share2 className="w-4 h-4 mr-2" /> Share
            </Button>
          </div>
        </header>

        {/* Main Content */}
        <div className="flex-1 relative bg-slate-950 overflow-hidden">
          {/* Background Grid */}
          <div 
            className="absolute inset-0 opacity-20 pointer-events-none"
            style={{
              backgroundImage: `linear-gradient(#334155 1px, transparent 1px), linear-gradient(90deg, #334155 1px, transparent 1px)`,
              backgroundSize: '40px 40px'
            }}
          />

          {/* Placeholder for D3/Mermaid Graph */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="w-24 h-24 mx-auto rounded-full bg-blue-500/20 border border-blue-500/50 flex items-center justify-center animate-pulse">
                <div className="w-16 h-16 rounded-full bg-blue-500/40 flex items-center justify-center">
                  <div className="w-8 h-8 rounded-full bg-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.5)]" />
                </div>
              </div>
              <h2 className="text-2xl font-bold text-white">Interactive Graph Visualization</h2>
              <p className="text-slate-400 max-w-md">
                Enter a citation above to generate a dynamic precedent network graph.
                Visualize relationships, treatment signals, and influence paths.
              </p>
            </div>
          </div>

          {/* Controls Overlay */}
          <div className="absolute bottom-8 right-8 flex flex-col gap-2">
            <Button variant="secondary" size="icon" className="h-10 w-10 shadow-lg bg-white/10 hover:bg-white/20 text-white border-white/10 backdrop-blur-sm">
              <ZoomIn className="w-5 h-5" />
            </Button>
            <Button variant="secondary" size="icon" className="h-10 w-10 shadow-lg bg-white/10 hover:bg-white/20 text-white border-white/10 backdrop-blur-sm">
              <ZoomOut className="w-5 h-5" />
            </Button>
            <Button variant="secondary" size="icon" className="h-10 w-10 shadow-lg bg-white/10 hover:bg-white/20 text-white border-white/10 backdrop-blur-sm">
              <Maximize className="w-5 h-5" />
            </Button>
          </div>

          {/* Legend Overlay */}
          <Card className="absolute bottom-8 left-8 w-64 bg-slate-900/90 border-slate-800 text-slate-200 backdrop-blur-md shadow-xl">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Legend</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
                <span>Positive Treatment</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" />
                <span>Negative Treatment</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-slate-400" />
                <span>Neutral / Cited</span>
              </div>
              <div className="h-px bg-slate-800 my-2" />
              <div className="flex items-center gap-2">
                <span className="w-8 h-0.5 bg-slate-500" />
                <span>Direct Citation</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
