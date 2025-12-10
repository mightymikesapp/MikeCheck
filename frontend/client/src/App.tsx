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

// NOTE: About Theme
// - First choose a default theme according to your design style (dark or light bg), than change color palette in index.css
//   to keep consistent foreground/background color across components
// - If you want to make theme switchable, pass `switchable` ThemeProvider and use `useTheme` hook

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider
        defaultTheme="light"
        // switchable
      >
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
