import { useState } from "react";
import Layout from "@/components/Layout";
import { 
  ResizableHandle, 
  ResizablePanel, 
  ResizablePanelGroup 
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  Search, 
  ArrowLeft,
  Maximize2,
  Minimize2,
  Download,
  Share2,
  Network
} from "lucide-react";
import { cn } from "@/lib/utils";

// Mock data for demonstration
const MOCK_CITATIONS = [
  {
    id: 1,
    text: "Roe v. Wade, 410 U.S. 113 (1973)",
    status: "overruled",
    confidence: 0.98,
    page: 4,
    context: "...as established in Roe v. Wade, 410 U.S. 113 (1973), the right to privacy...",
    treatment: {
      summary: "Overruled by Dobbs v. Jackson Women's Health Organization",
      signals: { negative: 5, positive: 12, neutral: 45 }
    }
  },
  {
    id: 2,
    text: "Marbury v. Madison, 5 U.S. 137 (1803)",
    status: "verified",
    confidence: 0.99,
    page: 2,
    context: "...foundational principle of judicial review from Marbury v. Madison...",
    treatment: {
      summary: "Good Law - Foundational Case",
      signals: { negative: 0, positive: 1500, neutral: 500 }
    }
  },
  {
    id: 3,
    text: "Chevron U.S.A., Inc. v. NRDC, 467 U.S. 837 (1984)",
    status: "questioned",
    confidence: 0.85,
    page: 8,
    context: "...deference to agency interpretation under Chevron...",
    treatment: {
      summary: "Questioned by Loper Bright Enterprises v. Raimondo",
      signals: { negative: 2, positive: 800, neutral: 200 }
    }
  }
];

export default function DocumentReview() {
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const activeCitation = MOCK_CITATIONS.find(c => c.id === selectedCitation);

  return (
    <Layout>
      <div className="h-screen flex flex-col bg-background overflow-hidden">
        {/* Toolbar */}
        <header className="h-14 border-b border-border bg-background flex items-center justify-between px-4 shrink-0 z-20">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div className="flex flex-col">
              <h1 className="text-sm font-bold text-foreground">Smith_v_Jones_Brief.pdf</h1>
              <span className="text-xs text-muted-foreground">Last edited 2 hours ago</span>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 px-3 py-1.5 bg-accent/50 rounded text-xs font-medium">
              <span className="w-2 h-2 rounded-full bg-green-500" />
              12 Verified
            </div>
            <div className="flex items-center gap-1 px-3 py-1.5 bg-accent/50 rounded text-xs font-medium">
              <span className="w-2 h-2 rounded-full bg-destructive" />
              1 Overruled
            </div>
            <div className="h-6 w-px bg-border mx-2" />
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Share2 className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Download className="w-4 h-4" />
            </Button>
          </div>
        </header>

        {/* Main Workspace */}
        <ResizablePanelGroup direction="horizontal" className="flex-1">
          
          {/* Document Viewer (Left) */}
          <ResizablePanel defaultSize={60} minSize={30}>
            <div className="h-full bg-accent/10 flex flex-col relative">
              <div className="absolute top-4 right-4 z-10 flex gap-2">
                <Button 
                  variant="secondary" 
                  size="icon" 
                  className="h-8 w-8 shadow-sm bg-background"
                  onClick={() => setIsFullscreen(!isFullscreen)}
                >
                  {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </Button>
              </div>
              
              <ScrollArea className="flex-1 p-8">
                <div className="max-w-3xl mx-auto bg-white shadow-sm min-h-[1000px] p-12 font-serif text-lg leading-relaxed text-gray-900">
                  {/* Mock Document Content */}
                  <h1 className="text-2xl font-bold mb-8 text-center">BRIEF FOR PETITIONER</h1>
                  
                  <p className="mb-6">
                    The principle of judicial review, as established in 
                    <span 
                      className={cn(
                        "mx-1 px-1 rounded cursor-pointer transition-colors border-b-2",
                        selectedCitation === 2 
                          ? "bg-green-100 border-green-500" 
                          : "bg-transparent border-transparent hover:bg-green-50 hover:border-green-200"
                      )}
                      onClick={() => setSelectedCitation(2)}
                    >
                      Marbury v. Madison, 5 U.S. 137 (1803)
                    </span>
                    , remains the cornerstone of our constitutional architecture. It is the province and duty of the judicial department to say what the law is.
                  </p>

                  <p className="mb-6">
                    However, the right to privacy discussed in
                    <span 
                      className={cn(
                        "mx-1 px-1 rounded cursor-pointer transition-colors border-b-2",
                        selectedCitation === 1 
                          ? "bg-red-100 border-destructive" 
                          : "bg-transparent border-transparent hover:bg-red-50 hover:border-red-200"
                      )}
                      onClick={() => setSelectedCitation(1)}
                    >
                      Roe v. Wade, 410 U.S. 113 (1973)
                    </span>
                    has undergone significant jurisprudential evolution.
                  </p>

                  <p className="mb-6">
                    Furthermore, administrative law principles regarding
                    <span 
                      className={cn(
                        "mx-1 px-1 rounded cursor-pointer transition-colors border-b-2",
                        selectedCitation === 3 
                          ? "bg-orange-100 border-orange-500" 
                          : "bg-transparent border-transparent hover:bg-orange-50 hover:border-orange-200"
                      )}
                      onClick={() => setSelectedCitation(3)}
                    >
                      Chevron U.S.A., Inc. v. NRDC
                    </span>
                    are currently under intense scrutiny by this Court.
                  </p>
                  
                  {/* Filler text */}
                  {Array.from({ length: 5 }).map((_, i) => (
                    <p key={i} className="mb-6 text-gray-400">
                      [Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.]
                    </p>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>

          <ResizableHandle />

          {/* Analysis Panel (Right) */}
          <ResizablePanel defaultSize={40} minSize={20}>
            <div className="h-full flex flex-col bg-background border-l border-border">
              <Tabs defaultValue="citations" className="flex-1 flex flex-col">
                <div className="px-4 pt-4 border-b border-border">
                  <TabsList className="w-full justify-start bg-transparent p-0 h-auto gap-6">
                    <TabsTrigger 
                      value="citations" 
                      className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3 font-medium"
                    >
                      Citations ({MOCK_CITATIONS.length})
                    </TabsTrigger>
                    <TabsTrigger 
                      value="quotes" 
                      className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3 font-medium"
                    >
                      Quotes (0)
                    </TabsTrigger>
                    <TabsTrigger 
                      value="strengthen" 
                      className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3 font-medium"
                    >
                      Strengthen
                    </TabsTrigger>
                  </TabsList>
                </div>

                <TabsContent value="citations" className="flex-1 flex flex-col m-0 p-0 overflow-hidden">
                  {activeCitation ? (
                    <div className="flex-1 flex flex-col overflow-hidden animate-in slide-in-from-right-4 duration-300">
                      {/* Detail View Header */}
                      <div className="p-6 border-b border-border bg-accent/10">
                        <div className="flex items-start justify-between mb-4">
                          <Button 
                            variant="ghost" 
                            size="sm" 
                            className="-ml-2 text-muted-foreground"
                            onClick={() => setSelectedCitation(null)}
                          >
                            <ArrowLeft className="w-4 h-4 mr-1" /> Back to List
                          </Button>
                          <div className={cn(
                            "px-2 py-1 rounded text-xs font-bold uppercase tracking-wide",
                            activeCitation.status === "verified" && "bg-green-100 text-green-700",
                            activeCitation.status === "overruled" && "bg-red-100 text-red-700",
                            activeCitation.status === "questioned" && "bg-orange-100 text-orange-700",
                          )}>
                            {activeCitation.status}
                          </div>
                        </div>
                        
                        <h2 className="text-lg font-bold font-serif mb-2">{activeCitation.text}</h2>
                        <p className="text-sm text-muted-foreground">{activeCitation.treatment.summary}</p>
                      </div>

                      {/* Detail View Content */}
                      <ScrollArea className="flex-1 p-6">
                        <div className="space-y-8">
                          {/* Treatment Signals */}
                          <div className="space-y-3">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Treatment Signals</h3>
                            <div className="grid grid-cols-3 gap-4">
                              <div className="p-3 bg-accent/30 rounded border border-border text-center">
                                <div className="text-2xl font-bold text-green-600">{activeCitation.treatment.signals.positive}</div>
                                <div className="text-xs text-muted-foreground">Positive</div>
                              </div>
                              <div className="p-3 bg-accent/30 rounded border border-border text-center">
                                <div className="text-2xl font-bold text-destructive">{activeCitation.treatment.signals.negative}</div>
                                <div className="text-xs text-muted-foreground">Negative</div>
                              </div>
                              <div className="p-3 bg-accent/30 rounded border border-border text-center">
                                <div className="text-2xl font-bold text-foreground">{activeCitation.treatment.signals.neutral}</div>
                                <div className="text-xs text-muted-foreground">Neutral</div>
                              </div>
                            </div>
                          </div>

                          {/* Context */}
                          <div className="space-y-3">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Context in Document</h3>
                            <div className="p-4 bg-accent/30 rounded border border-border font-serif text-sm italic text-muted-foreground">
                              "{activeCitation.context}"
                            </div>
                            <div className="flex justify-end">
                              <Button variant="outline" size="sm" className="text-xs">
                                Jump to Page {activeCitation.page}
                              </Button>
                            </div>
                          </div>

                          {/* Actions */}
                          <div className="space-y-3">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Actions</h3>
                            <div className="flex flex-col gap-2">
                              <Button className="w-full justify-start">
                                <Network className="w-4 h-4 mr-2" /> View Citation Network
                              </Button>
                              <Button variant="outline" className="w-full justify-start">
                                <Search className="w-4 h-4 mr-2" /> Read Full Opinion
                              </Button>
                            </div>
                          </div>
                        </div>
                      </ScrollArea>
                    </div>
                  ) : (
                    <ScrollArea className="flex-1">
                      <div className="divide-y divide-border">
                        {MOCK_CITATIONS.map((citation) => (
                          <div 
                            key={citation.id}
                            className="p-4 hover:bg-accent/50 cursor-pointer transition-colors group"
                            onClick={() => setSelectedCitation(citation.id)}
                          >
                            <div className="flex items-start gap-3">
                              <div className="mt-1">
                                {citation.status === "verified" && <CheckCircle2 className="w-5 h-5 text-green-500" />}
                                {citation.status === "overruled" && <XCircle className="w-5 h-5 text-destructive" />}
                                {citation.status === "questioned" && <AlertTriangle className="w-5 h-5 text-orange-500" />}
                              </div>
                              <div className="flex-1 min-w-0">
                                <h3 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate">
                                  {citation.text}
                                </h3>
                                <p className="text-xs text-muted-foreground mt-1 truncate">
                                  {citation.treatment.summary}
                                </p>
                              </div>
                              <div className="text-xs text-muted-foreground font-mono">
                                p.{citation.page}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  )}
                </TabsContent>

                <TabsContent value="quotes" className="flex-1 p-8 flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 bg-accent rounded-full flex items-center justify-center mb-4">
                    <Search className="w-8 h-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-bold">No Quotes Detected</h3>
                  <p className="text-sm text-muted-foreground max-w-xs mt-2">
                    We couldn't find any direct quotes in this document section.
                  </p>
                </TabsContent>

                <TabsContent value="strengthen" className="flex-1 p-8 flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 bg-accent rounded-full flex items-center justify-center mb-4">
                    <Network className="w-8 h-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-bold">Strengthening Analysis</h3>
                  <p className="text-sm text-muted-foreground max-w-xs mt-2">
                    Select a paragraph to get AI-powered suggestions for stronger precedents.
                  </p>
                </TabsContent>
              </Tabs>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </Layout>
  );
}
