import { useState, type ReactNode } from "react";
import {
  CarFront,
  ChevronRight,
  CircleHelp,
  Globe2,
  Menu,
  MessageSquare,
  PackageSearch,
  Plus,
  Settings2,
  Sparkles,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { usePage } from "@/lib/page";
import { LinkButton, Notice } from "./shared";
const nav = [
  {
    href: "/",
    label: "Part requests",
    icon: PackageSearch,
    group: "workspace",
  },
  { href: "/cars", label: "Your garage", icon: CarFront, group: "workspace" },
  {
    href: "/websites",
    label: "Search sources",
    icon: Globe2,
    group: "workspace",
  },
  {
    href: "/ai",
    label: "AI connections",
    icon: Sparkles,
    group: "connections",
  },
  {
    href: "/discord",
    label: "Discord",
    icon: MessageSquare,
    group: "connections",
  },
  {
    href: "/settings",
    label: "Preferences",
    icon: Settings2,
    group: "connections",
  },
];
function Navigation({ path }: { path: string }) {
  return (
    <>
      <a className="brand" href="/" aria-label="R19 Finder home">
        <span className="brand-mark">
          <Wrench size={21} />
        </span>
        <span>
          R19<span className="brand-light">Finder</span>
          <small>THE PARTS WORKSPACE</small>
        </span>
      </a>
      <LinkButton href="/requests/new" className="sidebar-create">
        <Plus size={17} />
        New part request
      </LinkButton>
      <nav aria-label="Main navigation">
        {["workspace", "connections"].map((group) => (
          <div className="nav-group" key={group}>
            <p>{group === "workspace" ? "Workspace" : "Configuration"}</p>
            {nav
              .filter((n) => n.group === group)
              .map(({ href, label, icon: Icon }) => {
                const active =
                  href === "/"
                    ? path === "/" || path.startsWith("/requests")
                    : path.startsWith(href);
                return (
                  <a
                    href={href}
                    className={`nav-item ${active ? "active" : ""}`}
                    key={href}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon size={18} />
                    <span>{label}</span>
                    {active && <ChevronRight size={14} />}
                  </a>
                );
              })}
          </div>
        ))}
      </nav>
    </>
  );
}
export function Shell({ children }: { children: ReactNode }) {
  const { path, messages } = usePage();
  const [dismissed, setDismissed] = useState<number[]>([]);
  const current = nav.find((n) =>
    n.href === "/"
      ? path === "/" || path.startsWith("/requests")
      : path.startsWith(n.href),
  );
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Navigation path={path} />
      </aside>
      <div className="app-frame">
        <div className="topbar">
          <div className="topbar-location">
            <Sheet>
              <SheetTrigger asChild>
                <Button
                  className="mobile-menu"
                  variant="ghost"
                  size="icon"
                  aria-label="Open navigation"
                >
                  <Menu />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="mobile-sidebar">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <Navigation path={path} />
              </SheetContent>
            </Sheet>
            <span className="desktop-crumb">Workspace</span>
            <ChevronRight className="desktop-crumb" size={14} />
            <span>{current?.label || "Workspace"}</span>
          </div>
          <a href="/ai" className="topbar-help">
            <CircleHelp size={16} />
            <span>Connection settings</span>
          </a>
        </div>
        <main id="main-content" tabIndex={-1}>
          {messages.map(
            (message, i) =>
              !dismissed.includes(i) && (
                <Notice
                  key={i}
                  onDismiss={() => setDismissed([...dismissed, i])}
                >
                  {message}
                </Notice>
              ),
          )}
          {children}
        </main>
      </div>
    </>
  );
}
