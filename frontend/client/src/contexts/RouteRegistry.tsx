import { createContext, useContext, useMemo } from "react";

interface RouteRegistryProviderProps {
  children: React.ReactNode;
  routes: Array<string | undefined>;
}

const RouteRegistryContext = createContext<string[]>([]);

export function RouteRegistryProvider({ children, routes }: RouteRegistryProviderProps) {
  const normalizedRoutes = useMemo(
    () => Array.from(new Set(routes.filter((route): route is string => Boolean(route)))),
    [routes]
  );

  return (
    <RouteRegistryContext.Provider value={normalizedRoutes}>
      {children}
    </RouteRegistryContext.Provider>
  );
}

export function useRegisteredRoutes() {
  return useContext(RouteRegistryContext);
}
