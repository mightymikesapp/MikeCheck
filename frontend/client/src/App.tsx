import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import type { RouteProps } from "wouter";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { RouteRegistryProvider } from "./contexts/RouteRegistry";
import { ThemeProvider } from "./contexts/ThemeContext";
import Dashboard from "./pages/Dashboard";
import DocumentReview from "./pages/DocumentReview";
import CitationNetwork from "./pages/CitationNetwork";
import Research from "./pages/Research";
import Settings from "./pages/Settings";

type AppRoute = {
  path?: string;
  component: NonNullable<RouteProps["component"]>;
};

const appRoutes: AppRoute[] = [
  { path: "/", component: Dashboard },
  { path: "/review", component: DocumentReview },
  { path: "/network", component: CitationNetwork },
  { path: "/research", component: Research },
  { path: "/settings", component: Settings },
  { component: NotFound },
];

function Router() {
  const definedRoutes = appRoutes.map(route => route.path);

  return (
    <RouteRegistryProvider routes={definedRoutes}>
      <Switch>
        {appRoutes.map(({ path, component: Component }, index) => (
          <Route
            key={path ?? `route-${index}`}
            path={path}
            component={Component}
          />
        ))}
      </Switch>
    </RouteRegistryProvider>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
