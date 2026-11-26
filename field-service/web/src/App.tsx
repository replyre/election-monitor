/** Composition. Production (the built app at /field/) uses the site's own session: public totals for
 * visitors, the field screens for admins. `npm run dev` keeps the demo shell (src/devshell). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "@/lib/theme";
import { DevSessionProvider } from "@/devshell/DevSession";
import { Shell } from "@/devshell/Shell";
import { SignIn } from "@/devshell/SignIn";
import { FieldRoutes } from "@/field/routes";
import { ProdApp } from "@/prod/ProdApp";

const client = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: (n, e) => n < 1 && (e as { status?: number })?.status !== 403 } },
});

export function App() {
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <BrowserRouter>
          {import.meta.env.DEV ? (
            <DevSessionProvider signInPage={<SignIn />}>
              <Shell>
                <FieldRoutes />
              </Shell>
            </DevSessionProvider>
          ) : (
            <ProdApp />
          )}
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
