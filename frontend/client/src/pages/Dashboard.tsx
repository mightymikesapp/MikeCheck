import { useState } from "react";
import Layout from "@/components/Layout";
import DocumentUploader from "@/components/DocumentUploader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { 
  ArrowRight, 
  Clock, 
  FileText, 
  ShieldCheck, 
  AlertTriangle,
  BarChart3
} from "lucide-react";
import { useLocation } from "wouter";
import { cn } from "@/lib/utils";

export default function Dashboard() {
  const [, setLocation] = useLocation();
  const [recentDocs] = useState([
    { id: 1, name: "Smith_v_Jones_Brief.pdf", date: "2 hours ago", status: "verified", citations: 12, issues: 0 },
    { id: 2, name: "Appeal_Draft_v3.docx", date: "Yesterday", status: "warning", citations: 45, issues: 3 },
    { id: 3, name: "Memo_re_Compliance.pdf", date: "2 days ago", status: "verified", citations: 8, issues: 0 },
  ]);

  const handleUploadComplete = () => {
    // In a real app, we'd pass the file ID
    setTimeout(() => setLocation("/review"), 1000);
  };

  return (
    <Layout>
      <div className="flex-1 p-8 bg-background overflow-y-auto">
        <div className="max-w-6xl mx-auto space-y-12">
          
          {/* Hero Section */}
          <section className="space-y-6">
            <div className="space-y-2">
              <h1 className="text-4xl font-bold tracking-tight text-foreground">
                Legal Verification <span className="text-muted-foreground">Workbench</span>
              </h1>
              <p className="text-lg text-muted-foreground max-w-2xl">
                Upload your legal documents to verify citations, check quotes, and analyze treatment history with Swiss precision.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2">
                <DocumentUploader onUploadComplete={handleUploadComplete} />
              </div>
              
              <div className="space-y-4">
                <Card className="bg-primary text-primary-foreground border-none shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <ShieldCheck className="w-5 h-5" />
                      System Status
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-sm opacity-80">CourtListener API</span>
                      <span className="flex items-center gap-1.5 text-xs font-bold bg-green-500/20 px-2 py-1 rounded text-green-300">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                        ONLINE
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm opacity-80">Vector Store</span>
                      <span className="flex items-center gap-1.5 text-xs font-bold bg-green-500/20 px-2 py-1 rounded text-green-300">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                        READY
                      </span>
                    </div>
                    <div className="pt-4 border-t border-primary-foreground/10">
                      <div className="text-2xl font-bold">14,203</div>
                      <div className="text-xs opacity-70">Cases Indexed Today</div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">Quick Actions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <Button variant="outline" className="w-full justify-start gap-2 h-10">
                      <Search className="w-4 h-4" />
                      Search Case Law
                    </Button>
                    <Button variant="outline" className="w-full justify-start gap-2 h-10">
                      <Network className="w-4 h-4" />
                      Build Citation Graph
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          </section>

          {/* Recent Activity */}
          <section className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold tracking-tight">Recent Activity</h2>
              <Button variant="ghost" className="text-sm text-muted-foreground hover:text-foreground">
                View All History <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {recentDocs.map((doc) => (
                <Card key={doc.id} className="group hover:border-primary/50 transition-colors cursor-pointer">
                  <CardHeader className="pb-3">
                    <div className="flex justify-between items-start">
                      <div className="p-2 bg-accent rounded-md group-hover:bg-primary/10 transition-colors">
                        <FileText className="w-5 h-5 text-foreground group-hover:text-primary" />
                      </div>
                      {doc.status === "verified" ? (
                        <span className="flex items-center gap-1 text-xs font-medium text-green-600 bg-green-50 px-2 py-1 rounded-full">
                          <CheckCircle2 className="w-3 h-3" /> Verified
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs font-medium text-orange-600 bg-orange-50 px-2 py-1 rounded-full">
                          <AlertTriangle className="w-3 h-3" /> Issues Found
                        </span>
                      )}
                    </div>
                    <CardTitle className="mt-4 text-base font-bold truncate" title={doc.name}>
                      {doc.name}
                    </CardTitle>
                    <CardDescription className="flex items-center gap-1 text-xs">
                      <Clock className="w-3 h-3" /> {doc.date}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between text-sm border-t border-border pt-3">
                      <div className="flex flex-col">
                        <span className="text-muted-foreground text-xs">Citations</span>
                        <span className="font-mono font-medium">{doc.citations}</span>
                      </div>
                      <div className="flex flex-col text-right">
                        <span className="text-muted-foreground text-xs">Issues</span>
                        <span className={cn("font-mono font-medium", doc.issues > 0 ? "text-destructive" : "text-foreground")}>
                          {doc.issues}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>

          {/* Features Grid */}
          <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 pt-8 border-t border-border">
            {[
              { icon: ShieldCheck, title: "Treatment Analysis", desc: "Shepardizing-style validity checks" },
              { icon: FileText, title: "Quote Verification", desc: "Exact & fuzzy match detection" },
              { icon: Network, title: "Citation Networks", desc: "Visual precedent mapping" },
              { icon: BarChart3, title: "Strengthening", desc: "AI-powered source suggestions" },
            ].map((feature, i) => (
              <div key={i} className="flex gap-4 items-start p-4 rounded-lg hover:bg-accent/30 transition-colors">
                <feature.icon className="w-6 h-6 text-primary shrink-0" />
                <div>
                  <h3 className="font-bold text-sm">{feature.title}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{feature.desc}</p>
                </div>
              </div>
            ))}
          </section>
        </div>
      </div>
    </Layout>
  );
}

import { Search, Network, CheckCircle2 } from "lucide-react";
