import { lazy, Suspense, useEffect, useState } from "react";
import {
  ArrowUpRight,
  CalendarClock,
  CarFront,
  Clock3,
  Plus,
  RefreshCw,
  Search,
  SquarePen,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Back,
  CheckField,
  CSRF,
  Empty,
  Field,
  FormChoice,
  Heading,
  LinkButton,
  Notice,
  Photo,
  PostForm,
  Section,
  Status,
} from "@/components/shared";
import { usePage, date, requestData, safeUrl } from "@/lib/page";
import type {
  Car,
  Listing,
  Order,
  PagePayload,
  Profile,
  Research,
  Schedule,
} from "@/lib/types";
const Report = lazy(() => import("@/components/report"));
interface DetailData {
  order: Order;
  car?: Car;
  photos: { id: string }[];
  found_parts: Listing[];
  blacklist: { id: string; url: string; title: string; reason: string }[];
  searches: Research[];
  schedules: Schedule[];
  models: string[];
  codex_models: Record<string, string[]>;
  weekdays: string[];
  active_search: boolean;
  discord_config: { enabled: boolean; configured: boolean };
  part_field_map: Record<string, [string, string, ...unknown[]]>;
}
export function ProfileDetails({
  profile,
  labels,
}: {
  profile?: Profile;
  labels?: Record<string, [string, string, ...unknown[]]>;
}) {
  if (!profile?.facts?.length) return null;
  return (
    <dl className="profile-details">
      {profile.facts.map((f) => (
        <div key={f.id}>
          <dt>{labels?.[f.field]?.[1] || f.field.replaceAll("_", " ")}</dt>
          <dd>
            {f.value}
            <small>
              {f.verification_status === "user_confirmed"
                ? "Confirmed by you"
                : f.origin === "ai"
                  ? "AI suggestion · unverified"
                  : "User supplied"}
            </small>
            {f.evidence?.map((e, i) => (
              <p key={i}>
                {e.url ? (
                  <a
                    href={safeUrl(e.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {e.note || e.url}
                  </a>
                ) : (
                  e.note
                )}
              </p>
            ))}
            {f.reason && <small>{f.reason}</small>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
function Listings({ d }: { d: DetailData }) {
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>
            Parts found <span className="count">{d.found_parts.length}</span>
          </h2>
          <p>Unique listings collected across completed searches.</p>
        </div>
      </div>
      {d.found_parts.length ? (
        <>
          <div className="listing-grid">
            {d.found_parts.map((part) => (
              <article className="listing-card" key={part.url}>
                <Photo
                  src={safeUrl(part.image_url)}
                  alt={part.title || "Seller photo"}
                />
                <div className="listing-body">
                  <div className="listing-meta">
                    <span>{part.condition || "Condition unknown"}</span>
                    <span>{part.provider}</span>
                  </div>
                  <h3>{part.title || "Part listing"}</h3>
                  <div>
                    <p className="listing-price">
                      {part.price || "Price not confirmed"}
                    </p>
                    <p className="help">
                      Shipping: {part.shipping_cost || "not confirmed"}
                    </p>
                  </div>
                  <p className="prose-copy">{part.description}</p>
                  <dl className="listing-facts">
                    <div>
                      <dt>Seller / location</dt>
                      <dd>
                        {part.seller || "Unknown seller"} ·{" "}
                        {part.location || "Unconfirmed"}
                      </dd>
                    </div>
                    <div>
                      <dt>Pickup</dt>
                      <dd>{part.pickup || "Unconfirmed"}</dd>
                    </div>
                    <div>
                      <dt>Shipping</dt>
                      <dd>{part.shipping || "Unconfirmed"}</dd>
                    </div>
                  </dl>
                  <p className="help">
                    {part.availability === "listed_available"
                      ? "Reported available when searched"
                      : "Availability not confirmed"}{" "}
                    · {date(part.found_at)}
                  </p>
                  <details>
                    <summary>Fitment & checks</summary>
                    <div className="detail-copy">
                      <p>
                        {part.compatibility ||
                          "Check references and mounting points with the seller."}
                      </p>
                      {part.variant_checks && <p>{part.variant_checks}</p>}
                      {part.visual_comparison && (
                        <p>{part.visual_comparison}</p>
                      )}
                      <p>
                        Photo comparison:{" "}
                        {part.visual_status?.replaceAll("_", " ") ||
                          "Not checked"}
                      </p>
                      {part.availability_evidence && (
                        <p>Stock evidence: {part.availability_evidence}</p>
                      )}
                    </div>
                  </details>
                  <Button asChild className="w-full">
                    <a
                      href={safeUrl(part.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View seller listing
                      <ArrowUpRight size={16} />
                    </a>
                  </Button>
                  <details className="blacklist-control">
                    <summary>Remove & blacklist</summary>
                    <PostForm action={`/requests/${d.order.id}/blacklist`}>
                      <input type="hidden" name="url" value={part.url} />
                      <Field
                        name="reason"
                        label="Reason (optional)"
                        maxLength={500}
                        placeholder="Wrong version, already sold…"
                      />
                      <p className="help mb-3">
                        Hides this listing from this request and future results.
                        You can restore it below.
                      </p>
                      <Button variant="destructive" type="submit">
                        Confirm removal
                      </Button>
                    </PostForm>
                  </details>
                </div>
              </article>
            ))}
          </div>
          <p className="help mt-4">
            AI-reported results. Confirm fitment, price and stock with the
            seller.
          </p>
        </>
      ) : (
        <Empty
          icon={Search}
          title="No listings found yet"
          description="Start a search to collect listings, compare fitment and check seller details."
          action={
            <LinkButton href="#research">
              <Search size={16} />
              Start a search
            </LinkButton>
          }
        />
      )}{" "}
      {!!d.blacklist.length && (
        <Section className="mt-6">
          <details>
            <summary>
              Blacklist · {d.blacklist.length} hidden{" "}
              {d.blacklist.length === 1 ? "listing" : "listings"}
            </summary>
            <p className="help my-4">
              Excluded from future searches for this request. Original search
              reports keep their historical results.
            </p>
            {d.blacklist.map((e) => (
              <div className="delivery-row" key={e.id}>
                <div>
                  <a
                    className="text-link"
                    href={safeUrl(e.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {e.title || "Blocked listing"}
                  </a>
                  <p className="help">{e.reason}</p>
                </div>
                <PostForm
                  action={`/requests/${d.order.id}/blacklist/${e.id}/restore`}
                >
                  <Button variant="outline" type="submit">
                    Restore
                  </Button>
                </PostForm>
              </div>
            ))}
          </details>
        </Section>
      )}
    </>
  );
}
function ResearchForm({ d }: { d: DetailData }) {
  const [provider, setProvider] = useState("codex");
  const [model, setModel] = useState("");
  const [effort, setEffort] = useState("");
  return (
    <Section
      title="Search for this part"
      description={`Uses this request, vehicle specifications and ${d.photos.length} reference photo(s).`}
    >
      <div className="research-links">
        <PostForm action={`/requests/${d.order.id}/search/models`}>
          <Button variant="ghost" type="submit" size="sm">
            <RefreshCw size={14} />
            Refresh Open WebUI models
          </Button>
        </PostForm>
        <a className="text-link" href="/ai">
          Connection settings
        </a>
      </div>
      <PostForm action={`/requests/${d.order.id}/search`}>
        <div className="field-grid">
          <FormChoice
            name="model"
            label="AI provider & model"
            value={provider}
            onValueChange={setProvider}
            options={[
              { value: "codex", label: "Codex CLI" },
              ...d.models.map((m) => ({
                value: "openwebui:" + m,
                label: "Open WebUI · " + m,
              })),
            ]}
          />
          {provider === "codex" && (
            <>
              <FormChoice
                name="codex_model"
                label="Codex model"
                value={model}
                onValueChange={(v) => {
                  setModel(v);
                  setEffort("");
                }}
                options={[
                  { value: "", label: "Account default" },
                  ...Object.keys(d.codex_models).map((m) => ({
                    value: m,
                    label: m,
                  })),
                ]}
              />
              <FormChoice
                name="reasoning_effort"
                label="Reasoning effort"
                value={effort}
                onValueChange={setEffort}
                options={[
                  { value: "", label: "Model default" },
                  ...(d.codex_models[model] || []).map((v) => ({
                    value: v,
                    label: v,
                  })),
                ]}
                help="Higher effort can use more time and credits."
              />
            </>
          )}
        </div>
        <div className="field-grid">
          <Field
            name="preferred_options"
            label="Preferred number of options"
            type="number"
            min={1}
            max={20}
            step={1}
            defaultValue={6}
            required
            help="1–20 listings. Fewer may be returned."
          />
          <Field
            name="preferred_price"
            label="Preferred price (optional)"
            maxLength={80}
            placeholder="E.g. €150"
            help="Include currency. This is a preference, not a price limit."
          />
        </div>
        <details className="form-disclosure">
          <summary>Location & extra preferences</summary>
          <div className="field-grid mt-5">
            <Field
              name="pickup_areas"
              label="In-person pickup areas"
              maxLength={500}
              placeholder="Northern Portugal / Galicia"
            />
            <Field
              name="shipping_areas"
              label="Seller countries or regions for shipping"
              maxLength={500}
              placeholder="Europe"
            />
          </div>
          <Field
            name="instructions"
            label="Additional instructions"
            textarea
            rows={4}
            maxLength={4000}
            placeholder="Delivery destination, preferred condition, other details…"
          />
          <p className="help">
            Pickup and shipping can both be used. Leave areas blank for no
            preference.
          </p>
        </details>
        <p className="help mt-5 mb-4">
          Checks <a href="/websites">priority websites</a> first. Sends this
          request and photos to the selected provider and may use account
          credits.
        </p>
        <Button type="submit" disabled={d.active_search}>
          <Search size={16} />
          {d.active_search ? "Search in progress" : "Search for this part"}
        </Button>
        <details className="form-disclosure mt-6">
          <summary>
            <CalendarClock size={17} />
            Create a weekly schedule
          </summary>
          <p className="help mt-4 mb-5">
            Europe/Lisbon time. Saves these search settings and uses the latest
            request and photos.
          </p>
          <div className="schedule-days">
            {d.weekdays.map((day, i) => (
              <div key={day}>
                <CheckField label={day} name="weekdays" value={String(i)} />
                <Field
                  name={`time_${i}`}
                  label={`${day} time`}
                  type="time"
                  defaultValue="16:30"
                />
              </div>
            ))}
          </div>
          <CheckField
            name="discord_notify"
            label="Send new discoveries to Discord"
          />
          <p className="help my-4">
            Keep the app running. Scheduled searches may use credits. Saving a
            schedule does not start a search.{" "}
            <a href="/discord">Configure Discord</a>
          </p>
          <Button name="action" value="schedule" type="submit">
            Save weekly schedule
          </Button>
        </details>
      </PostForm>
    </Section>
  );
}
function Schedules({ d }: { d: DetailData }) {
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>Weekly schedules</h2>
          <p>All schedule times use Europe/Lisbon.</p>
        </div>
        <LinkButton href="#research" variant="outline">
          <Plus size={16} />
          Create schedule
        </LinkButton>
      </div>
      {d.schedules.length ? (
        d.schedules.map((s) => (
          <Section
            key={s.id}
            className="mb-4"
            title={`${d.weekdays[s.weekday]} · ${s.local_time.slice(0, 5)}`}
            action={
              <Status
                status={s.enabled ? "ok" : "untested"}
                label={s.enabled ? "Enabled" : "Paused"}
              />
            }
          >
            <p className="help">
              {String(s.settings.provider)} ·{" "}
              {s.settings.model || "Default model"} ·{" "}
              {s.settings.preferred_options} preferred options
            </p>
            {s.enabled && (
              <p className="help mt-2">
                Next run:{" "}
                {new Intl.DateTimeFormat("en-GB", {
                  dateStyle: "medium",
                  timeStyle: "short",
                  timeZone: "Europe/Lisbon",
                }).format(new Date(s.next_run))}
              </p>
            )}
            {s.last_message && <p className="help mt-2">{s.last_message}</p>}
            <PostForm
              action={`/requests/${d.order.id}/schedules/${s.id}`}
              className="schedule-notify"
            >
              <input type="hidden" name="action" value="discord" />
              <CheckField
                name="discord_notify"
                label="Discord notifications"
                defaultChecked={s.discord_notify}
              />
              <Button variant="outline" type="submit" size="sm">
                Save
              </Button>
            </PostForm>
            <details className="my-4">
              <summary>Saved search preferences</summary>
              <dl className="spec-grid mt-4">
                {Object.entries(s.settings).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k.replaceAll("_", " ")}</dt>
                    <dd>{Array.isArray(v) ? v.join(", ") : v || "None"}</dd>
                  </div>
                ))}
              </dl>
            </details>
            <div className="actions">
              <PostForm action={`/requests/${d.order.id}/schedules/${s.id}`}>
                <Button
                  variant="outline"
                  name="action"
                  value={s.enabled ? "disable" : "enable"}
                  type="submit"
                >
                  {s.enabled ? "Pause schedule" : "Enable schedule"}
                </Button>
              </PostForm>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost">
                    <Trash2 size={15} />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this schedule?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Future searches at this time will stop. Existing search
                      results will remain.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep schedule</AlertDialogCancel>
                    <form
                      method="post"
                      action={`/requests/${d.order.id}/schedules/${s.id}`}
                    >
                      <CSRF />
                      <input type="hidden" name="action" value="delete" />
                      <AlertDialogAction type="submit">
                        Delete schedule
                      </AlertDialogAction>
                    </form>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </Section>
        ))
      ) : (
        <Empty
          icon={CalendarClock}
          title="No scheduled searches"
          description="Set a weekly schedule to look again using your latest part details."
          action={<LinkButton href="#research">Create a schedule</LinkButton>}
        />
      )}
    </>
  );
}
function History({ d }: { d: DetailData }) {
  return (
    <>
      <div className="section-heading">
        <h2>
          Search history <span className="count">{d.searches.length}</span>
        </h2>
        <a
          href="#history"
          onClick={() => location.reload()}
          className="text-link"
        >
          <RefreshCw size={14} />
          Refresh
        </a>
      </div>
      {d.searches.length ? (
        d.searches.map((s) => (
          <Section key={s.id} className="history-entry mb-4">
            <div className="section-heading">
              <div>
                <h3>
                  {s.provider === "codex" ? "Codex CLI" : "Open WebUI"} ·{" "}
                  {s.model || "Default model"}
                </h3>
                <p>
                  {date(s.created_at, true)} UTC
                  {s.schedule_id ? " · Weekly search" : ""}
                </p>
              </div>
              <Status status={s.status} />
            </div>
            <details open={["queued", "running", "failed"].includes(s.status)}>
              <summary>
                View search report
                {s.listings?.length ? ` · ${s.listings.length} listings` : ""}
              </summary>
              <div className="report-body">
                {s.error && <Notice error>{s.error}</Notice>}
                {["queued", "running"].includes(s.status) && (
                  <Notice>
                    {s.status === "queued"
                      ? "Waiting for the research worker."
                      : "Researching the part. This can take several minutes."}{" "}
                    Status updates automatically.
                  </Notice>
                )}
                {s.research_meta?.rounds && (
                  <>
                    <p className="help">
                      Research round{" "}
                      {s.research_meta.current_round ||
                        s.research_meta.rounds.length}{" "}
                      / {s.research_meta.max_rounds} ·{" "}
                      {s.research_meta.new_listings} new listings{" "}
                      {s.research_meta.stop_reason &&
                        `· ${s.research_meta.stop_reason}`}
                    </p>
                    <details>
                      <summary>Research details & usage</summary>
                      <ul className="steps">
                        {s.research_meta.rounds.map((r) => (
                          <li key={r.number}>
                            Round {r.number}: {r.new_listings} new,{" "}
                            {r.filtered_listings} filtered · {r.status}{" "}
                            {r.remote_url && (
                              <a
                                href={safeUrl(r.remote_url)}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Provider conversation
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                      <p className="help">
                        Reported usage: {s.research_meta.reported_tokens} tokens{" "}
                        {!s.research_meta.usage_complete &&
                          "(incomplete provider reporting)"}
                      </p>
                    </details>
                  </>
                )}
                {s.result && (
                  <>
                    <p className="help">
                      {s.web_search_observed
                        ? "The provider returned web search activity or sources."
                        : "No evidence of web search was returned. Treat suggestions as unverified."}
                    </p>
                    <Suspense
                      fallback={<p className="help">Loading report…</p>}
                    >
                      <Report>{s.result}</Report>
                    </Suspense>
                  </>
                )}
                {s.sources?.length ? (
                  <div>
                    <h3>Sources</h3>
                    <ol className="steps">
                      {s.sources.map((source) => (
                        <li key={source}>
                          <a
                            href={safeUrl(source)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {source}
                          </a>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                {s.remote_url && (
                  <a
                    className="text-link"
                    href={safeUrl(s.remote_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open provider conversation
                  </a>
                )}
                {!!s.listings?.length && (
                  <details>
                    <summary>
                      Listings from this search · {s.listings.length}
                    </summary>
                    <ul className="steps">
                      {s.listings.map((item) => (
                        <li key={item.url}>
                          <a
                            href={safeUrl(item.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {item.title || "View listing"}
                          </a>
                          <p>
                            {item.price || "Price not confirmed"} ·{" "}
                            {item.seller || "Unknown seller"} ·{" "}
                            {item.location || "Location unconfirmed"}
                          </p>
                          <p>
                            {item.compatibility ||
                              "Compatibility not confirmed"}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <details>
                  <summary>Request details used</summary>
                  <p className="prose-copy mt-4">{s.vehicle}</p>
                  <p className="prose-copy">{s.description}</p>
                  {s.car_profile && (
                    <>
                      <h3 className="mt-4 mb-4">Car profile snapshot</h3>
                      <dl className="spec-grid">
                        {Object.entries(s.car_profile).map(([k, v]) => (
                          <div key={k}>
                            <dt>{k.replaceAll("_", " ")}</dt>
                            <dd>{v || "Not specified"}</dd>
                          </div>
                        ))}
                      </dl>
                    </>
                  )}
                  <dl className="spec-grid mt-4">
                    {(
                      [
                        "reasoning_effort",
                        "instructions",
                        "preferred_options",
                        "preferred_price",
                        "pickup_areas",
                        "shipping_areas",
                        "priority_websites",
                      ] as const
                    ).map((k) => (
                      <div key={k}>
                        <dt>{k.replaceAll("_", " ")}</dt>
                        <dd>
                          {Array.isArray(s[k])
                            ? (s[k] as string[]).join(", ")
                            : s[k] || "Not specified"}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <ProfileDetails
                    profile={s.part_profile}
                    labels={d.part_field_map}
                  />
                  {s.language_preferences && (
                    <p className="help">
                      Response language:{" "}
                      {s.language_preferences.response_language} · Search
                      languages:{" "}
                      {s.language_preferences.search_languages?.join(", ") ||
                        "Not recorded"}
                    </p>
                  )}
                </details>
              </div>
            </details>
          </Section>
        ))
      ) : (
        <Empty
          icon={Clock3}
          title="No research history"
          description="Completed searches, source links and the details used will be saved here."
        />
      )}
    </>
  );
}
export default function RequestDetail() {
  const page = usePage<DetailData>();
  const [d, setD] = useState(page.data);
  const [tab, setTab] = useState(() => location.hash.slice(1) || "parts");
  const [pollError, setPollError] = useState("");
  useEffect(() => {
    const sync = () => setTab(location.hash.slice(1) || "parts");
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => {
    if (!d.active_search) return;
    const controller = new AbortController();
    const timer = setInterval(async () => {
      if (document.hidden) return;
      try {
        const next = await requestData<PagePayload>(
          location.pathname,
          undefined,
          controller.signal,
        );
        setD(next.data as DetailData);
        setPollError("");
      } catch (e) {
        if (!controller.signal.aborted)
          setPollError(
            e instanceof Error ? e.message : "Unable to refresh status.",
          );
      }
    }, 5000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [d.active_search]);
  return (
    <>
      <Back />
      <Heading
        title={
          d.order.part_profile?.facts?.find((f) => f.field === "name")?.value ||
          d.order.vehicle ||
          "Part request"
        }
        description={`Part request · Added ${date(d.order.created_at)}`}
        action={
          <LinkButton variant="outline" href={`/requests/${d.order.id}/edit`}>
            <SquarePen size={16} />
            Edit request
          </LinkButton>
        }
      />
      <Section className="request-overview">
        <div>
          <p className="prose-copy">{d.order.description}</p>
          {d.car && (
            <a className="vehicle-link" href={`/cars/${d.car.id}`}>
              <CarFront size={16} />
              {d.car.name}
              <ArrowUpRight size={14} />
            </a>
          )}
          {!!d.order.part_profile?.facts?.length && (
            <details className="mt-4">
              <summary>Part details & references</summary>
              <ProfileDetails
                profile={d.order.part_profile}
                labels={d.part_field_map}
              />
            </details>
          )}
        </div>
        {d.photos.length > 0 && (
          <div className="reference-photos">
            {d.photos.map((p, i) => (
              <a
                key={p.id}
                href={`/photos/${p.id}`}
                target="_blank"
                rel="noopener"
              >
                <Photo
                  src={`/photos/${p.id}`}
                  alt={`Part reference photo ${i + 1}`}
                />
              </a>
            ))}
          </div>
        )}
      </Section>
      {pollError && <Notice error>{pollError} Retrying automatically.</Notice>}
      <Tabs
        value={
          ["parts", "research", "schedules", "history"].includes(tab)
            ? tab
            : "parts"
        }
        onValueChange={(v) => {
          setTab(v);
          history.replaceState(null, "", "#" + v);
        }}
        className="detail-tabs"
      >
        <TabsList>
          <TabsTrigger value="parts">
            Parts found <span>{d.found_parts.length}</span>
          </TabsTrigger>
          <TabsTrigger value="research">New search</TabsTrigger>
          <TabsTrigger value="schedules">
            Schedules <span>{d.schedules.length}</span>
          </TabsTrigger>
          <TabsTrigger value="history">
            History <span>{d.searches.length}</span>
          </TabsTrigger>
        </TabsList>
        <TabsContent value="parts">
          <Listings d={d} />
        </TabsContent>
        <TabsContent value="research">
          <ResearchForm d={d} />
        </TabsContent>
        <TabsContent value="schedules">
          <Schedules d={d} />
        </TabsContent>
        <TabsContent value="history">
          <History d={d} />
        </TabsContent>
      </Tabs>
    </>
  );
}
