import { useState } from "react";
import {
  ArrowDownUp,
  ArrowRight,
  CarFront,
  ChevronRight,
  Clock3,
  Package,
  Plus,
  Search,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePage, date } from "@/lib/page";
import type { Car, Order } from "@/lib/types";
import {
  ArrowLink,
  Empty,
  Gallery,
  Heading,
  LinkButton,
  Photo,
  Status,
} from "@/components/shared";
interface DashboardData {
  orders: Order[];
  cars: Car[];
  total: number;
  page: number;
  query: string;
  request_count: number;
  active_count: number;
}
export function RequestRows({ orders }: { orders: Order[] }) {
  return (
    <div className="request-list">
      {orders.map((order) => (
        <a
          className="request-row"
          href={`/requests/${order.id}`}
          key={order.id}
        >
          <div className="request-image">
            {order.cover_id ? (
              <Photo
                src={`/photos/${order.cover_id}`}
                alt={order.description}
              />
            ) : (
              <Package size={22} strokeWidth={1.3} />
            )}
          </div>
          <div className="request-copy">
            <h3>
              {order.part_profile?.facts?.find((f) => f.field === "name")
                ?.value || order.description}
            </h3>
            <p>{order.vehicle || "Vehicle not specified"}</p>
            <span className="mobile-date">{date(order.created_at)}</span>
          </div>
          <div className="request-status">
            <Status status={order.latest_status} />
          </div>
          <div className="request-date">
            <span>{date(order.created_at)}</span>
            <small>{order.photo_count || 0} photos</small>
          </div>
          <ChevronRight className="row-arrow" size={16} />
        </a>
      ))}
    </div>
  );
}
export function CarCard({
  car,
  compact = false,
}: {
  car: Car;
  compact?: boolean;
}) {
  return (
    <article className={`car-card ${compact ? "compact" : ""}`}>
      <Gallery
        photos={(car.photo_ids || []).map((p) => `/cars/${car.id}/photos/${p}`)}
        name={car.name}
      />
      <a className="car-caption" href={`/cars/${car.id}`}>
        <div>
          <h3>{car.name}</h3>
          <p>
            {[car.specs.year, car.specs.make, car.specs.model]
              .filter(Boolean)
              .join(" · ") || "Vehicle profile"}
          </p>
        </div>
        <ArrowRight size={17} />
      </a>
    </article>
  );
}
export default function Dashboard() {
  const { data: d } = usePage<DashboardData>();
  const [status, setStatus] = useState("all");
  const [oldest, setOldest] = useState(false);
  const filtered = d.orders.filter(
    (o) =>
      status === "all" ||
      (status === "active"
        ? ["queued", "running"].includes(o.latest_status || "")
        : o.latest_status === "completed"),
  );
  const orders = oldest ? [...filtered].reverse() : filtered;
  return (
    <>
      <Heading
        title="Your parts workspace"
        description="Track requests, review listings and manage your cars."
        action={
          <LinkButton href="/requests/new">
            <Plus size={17} />
            New part request
          </LinkButton>
        }
      />
      <div className="workspace-summary">
        <span>
          <Package size={15} />
          <strong>{d.request_count}</strong>{" "}
          {d.request_count === 1 ? "request" : "requests"}
        </span>
        <span>
          <CarFront size={16} />
          <strong>{d.cars.length}</strong>{" "}
          {d.cars.length === 1 ? "car" : "cars"} in your garage
        </span>
        <span>
          <Clock3 size={15} />
          <strong>{d.active_count}</strong> active{" "}
          {d.active_count === 1 ? "search" : "searches"}
        </span>
      </div>
      <div className="workspace-grid">
        <section className="requests-section" aria-labelledby="requests-title">
          <div className="section-heading">
            <h2 id="requests-title">
              Part requests <span className="count">{d.total}</span>
            </h2>
          </div>
          <div className="request-toolbar">
            <form action="/" role="search" className="search-input">
              <Search size={17} />
              <Input
                aria-label="Find a part or vehicle"
                name="q"
                defaultValue={d.query}
                placeholder="Find a part or vehicle…"
                type="search"
                maxLength={200}
              />
              {d.query && (
                <a href="/" aria-label="Clear search">
                  <X size={16} />
                </a>
              )}
              <Button
                variant="ghost"
                type="submit"
                size="icon"
                aria-label="Search requests"
              >
                <ArrowRight size={16} />
              </Button>
            </form>
            <Button
              variant="outline"
              size="icon"
              aria-label={oldest ? "Show newest first" : "Show oldest first"}
              onClick={() => setOldest(!oldest)}
              aria-pressed={oldest}
            >
              <ArrowDownUp size={16} />
            </Button>
          </div>
          <Tabs
            value={status}
            onValueChange={setStatus}
            className="filter-tabs"
          >
            <TabsList>
              <TabsTrigger value="all">All requests</TabsTrigger>
              <TabsTrigger value="active">In progress</TabsTrigger>
              <TabsTrigger value="completed">Results ready</TabsTrigger>
            </TabsList>
            <TabsContent value={status}>
              {status !== "all" && (
                <p className="help mb-3">Filtering requests on this page.</p>
              )}
              {orders.length ? (
                <>
                  <div className="list-labels">
                    <span>PART / VEHICLE</span>
                    <span>STATUS</span>
                    <span>ADDED</span>
                  </div>
                  <RequestRows orders={orders} />
                </>
              ) : (
                <Empty
                  title={
                    d.query || status !== "all"
                      ? "No matching requests"
                      : "No part requests yet"
                  }
                  description={
                    d.query || status !== "all"
                      ? "Try another search or switch to all requests."
                      : "Describe what you need, add a photo, and let your next search begin."
                  }
                  action={
                    d.query ? (
                      <LinkButton href="/" variant="outline">
                        Clear search
                      </LinkButton>
                    ) : status !== "all" ? (
                      <Button
                        variant="outline"
                        onClick={() => setStatus("all")}
                      >
                        Show all requests
                      </Button>
                    ) : (
                      <LinkButton href="/requests/new">
                        <Plus size={16} />
                        Create your first request
                      </LinkButton>
                    )
                  }
                />
              )}
            </TabsContent>
          </Tabs>
          <div className="pagination">
            <p>
              {d.total
                ? `Page ${d.page} of ${Math.ceil(d.total / 12)}`
                : "Your requests will appear here"}
            </p>
            <nav aria-label="Pagination">
              {d.page > 1 && (
                <LinkButton
                  variant="outline"
                  href={`/?page=${d.page - 1}&q=${encodeURIComponent(d.query)}`}
                >
                  Previous
                </LinkButton>
              )}
              {d.page * 12 < d.total && (
                <LinkButton
                  variant="outline"
                  href={`/?page=${d.page + 1}&q=${encodeURIComponent(d.query)}`}
                >
                  Next
                  <ChevronRight size={15} />
                </LinkButton>
              )}
            </nav>
          </div>
        </section>
        <aside className="garage-section" aria-labelledby="garage-title">
          <div className="section-heading">
            <h2 id="garage-title">Your garage</h2>
            <Button variant="ghost" size="icon" asChild>
              <a href="/cars/new" aria-label="Add car">
                <Plus size={17} />
              </a>
            </Button>
          </div>
          <div className="garage-stack">
            {d.cars.length ? (
              d.cars
                .slice(0, 3)
                .map((c) => <CarCard key={c.id} car={c} compact />)
            ) : (
              <div className="garage-empty">
                <CarFront size={38} strokeWidth={1.1} />
                <h3>No cars added</h3>
                <p>
                  Save its specifications once. Use them in every part search.
                </p>
                <LinkButton href="/cars/new" variant="outline">
                  <Plus size={15} />
                  Add a car
                </LinkButton>
              </div>
            )}
          </div>
          {d.cars.length > 0 && (
            <ArrowLink href="/cars">View your garage</ArrowLink>
          )}
        </aside>
      </div>
    </>
  );
}
