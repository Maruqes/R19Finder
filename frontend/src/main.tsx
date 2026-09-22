import { setNonce } from "get-nonce";
import { Component, lazy, Suspense, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { MotionConfig } from "motion/react";
import "@fontsource-variable/geist";
import "./styles.css";
import { PageContext } from "./lib/page";
import type { PagePayload } from "./lib/types";
import { Shell } from "./components/shell";
import { Empty, Heading, LinkButton } from "./components/shared";
import { Skeleton } from "./components/ui/skeleton";
import Dashboard from "./pages/dashboard";
const RequestForm = lazy(() => import("./pages/request-form"));
const RequestDetail = lazy(() => import("./pages/request-detail"));
const Cars = lazy(() =>
  import("./pages/cars").then((m) => ({ default: m.Cars })),
);
const CarForm = lazy(() =>
  import("./pages/cars").then((m) => ({ default: m.CarForm })),
);
const CarDetail = lazy(() =>
  import("./pages/cars").then((m) => ({ default: m.CarDetail })),
);
const Sources = lazy(() =>
  import("./pages/settings").then((m) => ({ default: m.Sources })),
);
const Preferences = lazy(() =>
  import("./pages/settings").then((m) => ({ default: m.Preferences })),
);
const Connections = lazy(() =>
  import("./pages/settings").then((m) => ({ default: m.Connections })),
);
const Discord = lazy(() =>
  import("./pages/settings").then((m) => ({ default: m.Discord })),
);
const pages: Record<string, React.ComponentType> = {
  index: Dashboard,
  new: RequestForm,
  detail: RequestDetail,
  cars: Cars,
  car_form: CarForm,
  car_detail: CarDetail,
  websites: Sources,
  settings: Preferences,
  ai: Connections,
  discord: Discord,
};
class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <>
        <Heading title="This page couldn’t load" />
        <Empty
          title="Let’s try that again"
          description="Reload the page to recover. Your saved requests and drafts are still available."
          action={<LinkButton href={location.href}>Reload page</LinkButton>}
        />
      </>
    ) : (
      this.props.children
    );
  }
}
const payload: PagePayload = JSON.parse(
  document.getElementById("page-data")?.textContent || "{}",
);
if (payload.nonce) setNonce(payload.nonce);
const Page = pages[payload.page];
createRoot(document.getElementById("root")!).render(
  <PageContext value={payload}>
    <MotionConfig reducedMotion="user">
      <Shell>
        <ErrorBoundary>
          <Suspense
            fallback={
              <div
                aria-busy="true"
                aria-label="Loading page"
                className="space-y-5"
              >
                <Skeleton className="h-10 w-64" />
                <Skeleton className="h-5 w-80 max-w-full" />
                <Skeleton className="h-80 w-full" />
              </div>
            }
          >
            {Page ? (
              <Page />
            ) : (
              <>
                <Heading title="We couldn’t open that page" />
                <Empty
                  title="Something needs attention"
                  description={
                    (payload.data as { message?: string })?.message ||
                    "This page is unavailable."
                  }
                  action={<LinkButton href="/">Back to requests</LinkButton>}
                />
              </>
            )}
          </Suspense>
        </ErrorBoundary>
      </Shell>
    </MotionConfig>
  </PageContext>,
);
