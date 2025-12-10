import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  User, 
  Shield, 
  Database, 
  Bell, 
  Key,
  Save
} from "lucide-react";

export default function Settings() {
  return (
    <Layout>
      <div className="flex-1 p-8 bg-background overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-8">
          
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-foreground">Settings</h1>
              <p className="text-muted-foreground mt-1">Manage your account, API keys, and preferences.</p>
            </div>
            <Button>
              <Save className="w-4 h-4 mr-2" /> Save Changes
            </Button>
          </div>

          <Tabs defaultValue="general" className="space-y-6">
            <TabsList className="w-full justify-start border-b border-border bg-transparent p-0 h-auto gap-6 rounded-none">
              <TabsTrigger 
                value="general" 
                className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3 font-medium"
              >
                General
              </TabsTrigger>
              <TabsTrigger 
                value="api" 
                className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3 font-medium"
              >
                API & Integrations
              </TabsTrigger>
              <TabsTrigger 
                value="analysis" 
                className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3 font-medium"
              >
                Analysis Preferences
              </TabsTrigger>
            </TabsList>

            <TabsContent value="general" className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <User className="w-5 h-5" /> Profile Information
                  </CardTitle>
                  <CardDescription>Update your personal details and contact info.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="firstName">First Name</Label>
                      <Input id="firstName" defaultValue="Legal" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="lastName">Last Name</Label>
                      <Input id="lastName" defaultValue="Researcher" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email Address</Label>
                    <Input id="email" type="email" defaultValue="researcher@firm.com" />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Bell className="w-5 h-5" /> Notifications
                  </CardTitle>
                  <CardDescription>Configure how you want to be alerted.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label className="text-base">Analysis Complete</Label>
                      <p className="text-sm text-muted-foreground">Receive an email when large documents finish processing.</p>
                    </div>
                    <Switch defaultChecked />
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label className="text-base">Critical Alerts</Label>
                      <p className="text-sm text-muted-foreground">Notify me immediately if a cited case is overruled.</p>
                    </div>
                    <Switch defaultChecked />
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="api" className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Key className="w-5 h-5" /> CourtListener API
                  </CardTitle>
                  <CardDescription>Configure your connection to the Free Law Project.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="apiKey">API Key</Label>
                    <div className="flex gap-2">
                      <Input id="apiKey" type="password" value="••••••••••••••••••••••••" readOnly />
                      <Button variant="outline">Update</Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Your key is stored securely. Last used: 2 minutes ago.
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Database className="w-5 h-5" /> Vector Store
                  </CardTitle>
                  <CardDescription>Manage your local embeddings database.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-accent/30 rounded-lg border border-border">
                    <div>
                      <div className="font-medium">ChromaDB Status</div>
                      <div className="text-sm text-muted-foreground">Local Instance</div>
                    </div>
                    <div className="flex items-center gap-2 text-green-600 text-sm font-medium">
                      <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                      Connected
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm">Clear Cache</Button>
                    <Button variant="outline" size="sm">Re-index Documents</Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="analysis" className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Shield className="w-5 h-5" /> Verification Thresholds
                  </CardTitle>
                  <CardDescription>Adjust the sensitivity of the analysis engine.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="flex justify-between">
                      <Label>Confidence Threshold</Label>
                      <span className="text-sm font-mono">85%</span>
                    </div>
                    <div className="h-2 bg-accent rounded-full overflow-hidden">
                      <div className="h-full bg-primary w-[85%]" />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Citations with confidence scores below this value will be flagged for manual review.
                    </p>
                  </div>

                  <div className="space-y-4">
                    <div className="flex justify-between">
                      <Label>Fuzzy Match Tolerance</Label>
                      <span className="text-sm font-mono">Strict</span>
                    </div>
                    <div className="h-2 bg-accent rounded-full overflow-hidden">
                      <div className="h-full bg-primary w-[90%]" />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Higher tolerance allows for more variation in quotes but may increase false positives.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </Layout>
  );
}
