import { useState } from "react";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { 
  Search, 
  Sparkles, 
  BookOpen, 
  ArrowRight,
  Library
} from "lucide-react";

export default function Research() {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSearching(true);
    // Simulate search
    setTimeout(() => setIsSearching(false), 2000);
  };

  return (
    <Layout>
      <div className="flex-1 p-8 bg-background overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-12">
          
          {/* Search Hero */}
          <section className="text-center space-y-6 py-12">
            <div className="w-16 h-16 mx-auto bg-primary/10 rounded-full flex items-center justify-center mb-6">
              <Library className="w-8 h-8 text-primary" />
            </div>
            <h1 className="text-4xl font-bold tracking-tight text-foreground">
              Semantic Legal Research
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Ask complex legal questions and find relevant case law using our advanced vector-based search engine.
            </p>

            <form onSubmit={handleSearch} className="max-w-2xl mx-auto relative">
              <div className="relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-primary to-blue-600 rounded-lg blur opacity-25 group-hover:opacity-50 transition duration-1000 group-hover:duration-200" />
                <div className="relative">
                  <Textarea 
                    placeholder="Describe the legal issue or fact pattern (e.g., 'Can a police officer search a vehicle without a warrant if they smell marijuana?')..." 
                    className="min-h-[120px] p-6 pr-32 text-lg resize-none shadow-xl border-0 focus-visible:ring-0 bg-background rounded-lg"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                  <div className="absolute bottom-4 right-4">
                    <Button 
                      type="submit" 
                      disabled={!query || isSearching}
                      className="rounded-full px-6 shadow-lg hover:shadow-xl transition-all"
                    >
                      {isSearching ? (
                        <Sparkles className="w-4 h-4 mr-2 animate-spin" />
                      ) : (
                        <Search className="w-4 h-4 mr-2" />
                      )}
                      Research
                    </Button>
                  </div>
                </div>
              </div>
            </form>
          </section>

          {/* Suggested Topics */}
          <section className="space-y-6">
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground text-center">Suggested Research Topics</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                "Qualified Immunity in 4th Amendment cases",
                "Chevron deference post-2024",
                "Fair Use in Generative AI copyright"
              ].map((topic, i) => (
                <Button 
                  key={i} 
                  variant="outline" 
                  className="h-auto py-4 px-6 text-left justify-between group hover:border-primary/50"
                  onClick={() => setQuery(topic)}
                >
                  <span className="truncate mr-2">{topic}</span>
                  <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity text-primary" />
                </Button>
              ))}
            </div>
          </section>

          {/* Recent Research */}
          <section className="space-y-6 pt-8 border-t border-border">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold tracking-tight">Recent Research</h2>
            </div>

            <div className="space-y-4">
              {[1, 2].map((i) => (
                <Card key={i} className="hover:bg-accent/30 transition-colors cursor-pointer">
                  <CardContent className="p-6">
                    <div className="flex items-start gap-4">
                      <div className="p-3 bg-primary/10 rounded-lg">
                        <BookOpen className="w-6 h-6 text-primary" />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-bold text-lg mb-1">Admissibility of digital evidence</h3>
                        <p className="text-muted-foreground text-sm line-clamp-2">
                          Research regarding the authentication requirements for social media posts used as evidence in criminal proceedings...
                        </p>
                        <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
                          <span>2 days ago</span>
                          <span>•</span>
                          <span>15 Cases Found</span>
                          <span>•</span>
                          <span className="text-green-600 font-medium">Report Generated</span>
                        </div>
                      </div>
                      <Button variant="ghost" size="icon">
                        <ArrowRight className="w-5 h-5" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        </div>
      </div>
    </Layout>
  );
}
