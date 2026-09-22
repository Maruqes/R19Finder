import { useEffect, useRef, useState } from "react";
import {
  Check,
  FileText,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
  Undo2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Back,
  CheckField,
  CSRF,
  Field,
  FormChoice,
  Heading,
  LinkButton,
  Notice,
  Photo,
  Section,
  UploadPhotos,
} from "@/components/shared";
import { usePage, requestData, safeUrl } from "@/lib/page";
import { merge, undoFill, type Change } from "@/lib/part-profile-merge";
import type { Car, Fact, Order, PartField, Profile } from "@/lib/types";
interface FormDataContext {
  order?: Order;
  photos?: { id: string }[];
  removed?: string[];
  description?: string;
  vehicle?: string;
  selected_car_id: string;
  cars: Car[];
  part_fields: PartField[];
  part_groups: string[];
  part_profile?: Profile;
  part_models: string[];
  part_codex_models: Record<string, string[]>;
  language_preferences: {
    response_language: string;
    search_languages: string[];
  };
  language_names: Record<string, string>;
  error?: string;
}
interface Draft {
  id: string;
  revision: number;
  request_id: string;
  saved_url?: string;
  content: {
    description: string;
    vehicle: string;
    car_id: string;
    part_profile: Profile;
    review_state?: Review;
  };
  photos: { id: string; url: string }[];
  run?: {
    id: string;
    status: string;
    provider: string;
    model: string;
    reasoning_effort: string;
  };
}
interface Review {
  pending: Fact[];
  handled: string[];
  undo: Change[];
}
interface Run {
  id: string;
  status: string;
  error?: string;
  progress?: {
    message: string;
    elapsed_seconds: number;
    queue_position: number;
    worker_online: boolean;
  };
  input: { car_id: string; vehicle: string; part_profile: Profile };
  output: {
    suggestions?: Fact[];
    missing_information?: string[];
    conflicts?: string[];
    limitations?: string[];
  };
}
const blankReview: Review = { pending: [], handled: [], undo: [] };
function uid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 15) | 64;
  b[8] = (b[8] & 63) | 128;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
function newFact(field: string): Fact {
  return {
    id: uid(),
    field,
    value: "",
    origin: "user",
    review_status: "accepted",
    verification_status: "unverified",
  };
}
export default function RequestForm() {
  const { data: d, csrf } = usePage<FormDataContext>();
  const form = useRef<HTMLFormElement>(null);
  const [description, setDescription] = useState(d.description || "");
  const [vehicle, setVehicle] = useState(d.vehicle || "");
  const [car, setCar] = useState(d.selected_car_id || "");
  const [facts, setFacts] = useState<Fact[]>(() =>
    d.part_fields.flatMap(([key]) => {
      const existing = d.part_profile?.facts?.filter((f) => f.field === key);
      return existing?.length ? existing : [newFact(key)];
    }),
  );
  const [rejected, setRejected] = useState(d.part_profile?.rejected || []);
  const [review, setReview] = useState<Review>(blankReview);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [run, setRun] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState(d.error || "");
  const [model, setModel] = useState("codex:");
  const [effort, setEffort] = useState("");
  const [includePhotos, setIncludePhotos] = useState(true);
  const [notes, setNotes] = useState<string[]>([]);
  const [resetKey, setResetKey] = useState(0);
  const [resumeId, setResumeId] = useState("");
  const cancelledRun = useRef<string | null>(null);
  const dirty = useRef(false);
  const editVersion = useRef(0);
  const busyRef = useRef(false);
  const latest = useRef({ facts, review, car, vehicle });
  latest.current = { facts, review, car, vehicle };
  const storageKey = "part-draft:" + (d.order?.id || "new");
  function changed() {
    dirty.current = true;
    editVersion.current++;
  }
  function store(id?: string) {
    try {
      if (id) sessionStorage.setItem(storageKey, id);
      else sessionStorage.removeItem(storageKey);
    } catch {
      /* The draft URL remains available. */
    }
  }
  function minimal(values: Record<string, string | number> = {}) {
    const data = new FormData();
    data.set("csrf", csrf);
    Object.entries(values).forEach(([k, v]) => data.set(k, String(v)));
    return data;
  }
  async function action(fn: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Something went wrong. Your edits are still here.",
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  async function saveDraft() {
    if (!form.current?.reportValidity())
      throw new Error(
        "Add a description of at least 10 characters before saving.",
      );
    const version = editVersion.current;
    const data = new FormData(form.current);
    data.set(
      "part_profile",
      JSON.stringify({
        schema_version: 1,
        facts: latest.current.facts.filter((f) => f.value.trim()),
        rejected: rejected.slice(-60),
      }),
    );
    data.set("review_state", JSON.stringify(latest.current.review));
    data.set("request_id", d.order?.id || "");
    if (d.order) data.set("profile_revision", String(d.order.profile_revision));
    if (draft) data.set("revision", String(draft.revision));
    const saved = await requestData<Draft>(
      draft ? `/part-drafts/${draft.id}/update` : "/part-drafts",
      data,
    );
    setDraft(saved);
    store(saved.id);
    const url = new URL(location.href);
    url.searchParams.set("draft", saved.id);
    history.replaceState(null, "", url);
    setResetKey((k) => k + 1);
    const invalidated = saved.content.part_profile.facts.filter(
      (f) => f.review_status === "pending",
    );
    setFacts((current) =>
      current.map((f) => {
        const server = invalidated.find((x) => x.id === f.id);
        return server
          ? {
              ...f,
              review_status: "pending",
              verification_status: "unverified",
            }
          : f;
      }),
    );
    dirty.current = version !== editVersion.current;
    if (dirty.current)
      throw new Error(
        "Edits made while saving are still in the form. Save again to include them.",
      );
    return saved;
  }
  function updateFact(id: string, patch: Partial<Fact>) {
    setFacts((current) =>
      current.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    );
    changed();
  }
  function dismiss(f: Fact) {
    setFacts((current) => current.filter((x) => x.id !== f.id));
    setReview((r) => ({
      ...r,
      pending: r.pending.filter((x) => x.id !== f.id),
      handled: [...new Set([...r.handled, f.id])].slice(-200),
    }));
    setRejected((r) => [...r, `${f.field}: ${f.value}`].slice(-60));
    changed();
  }
  function invalidateVehicle() {
    setFacts((current) =>
      current.map((f) =>
        f.origin === "ai"
          ? {
              ...f,
              review_status: "pending",
              verification_status: "unverified",
            }
          : f,
      ),
    );
    changed();
  }
  useEffect(() => {
    try {
      setResumeId(
        new URL(location.href).searchParams.get("draft") ||
          sessionStorage.getItem(storageKey) ||
          "",
      );
    } catch {
      /* storage unavailable */
    }
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [storageKey]);
  useEffect(() => {
    if (!run || !draft) return;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      if (document.hidden || busyRef.current) {
        timer = setTimeout(poll, 3000);
        return;
      }
      try {
        const result = await requestData<Run>(
          `/part-drafts/${draft!.id}/enrichments/${run}`,
          undefined,
          controller.signal,
        );
        if (controller.signal.aborted || cancelledRun.current === run) return;
        if (["queued", "running"].includes(result.status)) {
          setMessage(
            `${result.progress?.message || "Researching…"}${result.progress ? ` · ${Math.floor(result.progress.elapsed_seconds / 60)}m ${result.progress.elapsed_seconds % 60}s elapsed` : ""}`,
          );
          timer = setTimeout(poll, 3000);
          return;
        }
        setRun(null);
        if (result.status !== "completed") {
          setError(result.error || "AI fill cancelled. Your draft is safe.");
          return;
        }
        const current = latest.current;
        if (
          current.car !== (result.input.car_id || "") ||
          (!current.car && current.vehicle.trim() !== result.input.vehicle)
        ) {
          setMessage(
            "The vehicle changed during research. Suggestions were not applied. Run AI again with the current vehicle.",
          );
          return;
        }
        const merged = merge(
          current.facts,
          result.input.part_profile.facts || [],
          result.output.suggestions || [],
          d.part_fields.filter((f) => f[3]).map((f) => f[0]),
          current.review.handled,
        );
        setFacts(merged.facts);
        setReview({
          pending: [...current.review.pending, ...merged.pending],
          handled: merged.handled,
          undo: merged.undo,
        });
        setNotes([
          ...(result.output.missing_information || []),
          ...(result.output.conflicts || []),
          ...(result.output.limitations || []),
        ]);
        setMessage(
          "Suggestions are ready. Review them before saving the part.",
        );
        changed();
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(
            e instanceof Error
              ? e.message
              : "Unable to check AI status. Retrying shortly.",
          );
          timer = setTimeout(poll, 10000);
        }
      }
    }
    timer = setTimeout(poll, 1000);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [run, draft?.id]);
  function start(purpose: string) {
    void action(async () => {
      if (
        review.pending.length ||
        facts.some((f) => f.review_status === "pending")
      )
        throw new Error(
          "Review existing AI suggestions before starting another fill.",
        );
      const saved = await saveDraft();
      const result = await requestData<{ id: string }>(
        `/part-drafts/${saved.id}/enrichments`,
        minimal({
          revision: saved.revision,
          idempotency_key: uid(),
          model,
          reasoning_effort: effort,
          purpose,
          include_photos: includePhotos ? "on" : "",
        }),
      );
      cancelledRun.current = null;
      setRun(result.id);
      setReview((r) => ({ ...r, undo: [] }));
      setMessage("Request saved. Waiting for the AI worker…");
    });
  }
  async function resume() {
    const saved = await requestData<Draft>("/part-drafts/" + resumeId);
    if (saved.request_id !== (d.order?.id || ""))
      throw new Error(
        "This draft belongs to a different part. Open its original form.",
      );
    if (saved.saved_url) {
      location.assign(saved.saved_url);
      return;
    }
    setDraft(saved);
    setDescription(saved.content.description);
    setVehicle(saved.content.vehicle);
    setCar(saved.content.car_id);
    setFacts(saved.content.part_profile.facts);
    setRejected(saved.content.part_profile.rejected || []);
    setReview({ ...blankReview, ...saved.content.review_state });
    setResumeId("");
    store(saved.id);
    if (saved.run) {
      setModel(saved.run.provider + ":" + saved.run.model);
      setEffort(saved.run.reasoning_effort);
      setRun(saved.run.id);
    }
    dirty.current = false;
    setMessage("Draft restored.");
  }
  const pending = facts.filter((f) => f.review_status === "pending");
  function renderFact(f: Fact, label: string, multiple: boolean) {
    return (
      <div
        className={`fact-editor ${f.origin === "ai" ? "ai-fact" : ""}`}
        key={f.id}
      >
        {f.field === "buying_unit" ? (
          <FormChoice
            label={label}
            value={f.value}
            onValueChange={(v) =>
              updateFact(f.id, {
                value: v,
                verification_status: "unverified",
                identifier: null,
              })
            }
            options={["", "individual", "pair", "set", "unknown"].map((v) => ({
              value: v,
              label: v || "Not specified",
            }))}
          />
        ) : (
          <Field
            label={label}
            name={"part_" + f.field}
            textarea={f.field !== "quantity"}
            rows={2}
            type={f.field === "quantity" ? "number" : undefined}
            min={f.field === "quantity" ? 1 : undefined}
            max={f.field === "quantity" ? 999 : undefined}
            value={f.value}
            maxLength={1500}
            onChange={(e) =>
              updateFact(f.id, {
                value: e.target.value,
                verification_status: "unverified",
                identifier: null,
              })
            }
          />
        )}{" "}
        {f.origin === "ai" && (
          <>
            <Badge variant="outline">
              {f.review_status === "pending"
                ? "Review AI suggestion"
                : "AI suggestion · reviewed"}
            </Badge>
            {f.reason && <p className="help">{f.reason}</p>}
            {f.evidence?.map((e, i) => (
              <p key={i} className="help">
                {e.url ? (
                  <a
                    href={safeUrl(e.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {e.note || "View source"}
                  </a>
                ) : (
                  e.note
                )}
              </p>
            ))}
            {f.identifier && (
              <dl className="identifier-meta">
                {Object.entries(f.identifier)
                  .filter(([, v]) => v != null && v !== "")
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{k.replaceAll("_", " ")}</dt>
                      <dd>{Array.isArray(v) ? v.join("; ") : String(v)}</dd>
                    </div>
                  ))}
              </dl>
            )}
          </>
        )}
        <div className="fact-actions">
          {f.review_status === "pending" && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => updateFact(f.id, { review_status: "accepted" })}
            >
              <Check size={14} />
              Accept as unverified
            </Button>
          )}
          {f.value && (
            <CheckField
              label="I have confirmed this fact"
              checked={f.verification_status === "user_confirmed"}
              onCheckedChange={(v) =>
                updateFact(f.id, {
                  verification_status: v ? "user_confirmed" : "unverified",
                  ...(v ? { review_status: "accepted" } : {}),
                })
              }
            />
          )}{" "}
          {(multiple || f.origin === "ai") && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => dismiss(f)}
            >
              <Trash2 size={14} />
              {f.origin === "ai" ? "Dismiss" : "Remove"}
            </Button>
          )}
        </div>
      </div>
    );
  }
  return (
    <>
      <Back href={d.order ? `/requests/${d.order.id}` : "/"}>
        {d.order ? "Back to request" : "Back to requests"}
      </Back>
      <Heading
        title={d.order ? "Edit part request" : "What part are you looking for?"}
        description="Start with what you know. Build a clearer picture as you go."
      />
      <div className="form-layout">
        <form
          ref={form}
          onInput={changed}
          onSubmit={(e) => {
            e.preventDefault();
            void action(async () => {
              if (run)
                throw new Error(
                  "Wait for AI to finish or cancel it before saving.",
                );
              if (review.pending.length || pending.length)
                throw new Error(
                  "Review all highlighted suggestions and alternatives before saving.",
                );
              const saved = await saveDraft();
              if (
                saved.content.part_profile.facts.some(
                  (f) => f.review_status === "pending",
                )
              )
                throw new Error(
                  "The vehicle profile changed. Review the highlighted AI facts before saving.",
                );
              const result = await requestData<{ url: string }>(
                `/part-drafts/${saved.id}/commit`,
                minimal({ revision: saved.revision }),
              );
              dirty.current = false;
              store();
              location.assign(result.url);
            });
          }}
          className="form-main"
          aria-busy={busy}
        >
          <CSRF />
          {error && <Notice error>{error}</Notice>}
          {resumeId && (
            <Notice>
              <p>A saved draft is available in this browser session.</p>
              <div className="actions mt-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => void action(resume)}
                >
                  Resume draft
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    store();
                    setResumeId("");
                    const u = new URL(location.href);
                    u.searchParams.delete("draft");
                    history.replaceState(null, "", u);
                  }}
                >
                  Start fresh
                </Button>
              </div>
            </Notice>
          )}
          <fieldset disabled={busy} className="form-fieldset">
            <Section
              title="The part"
              description="A clear description is the best place to start."
            >
              <Field
                name="description"
                label="Description"
                textarea
                required
                minLength={10}
                maxLength={5000}
                rows={5}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="E.g. Left rear tail light for a Phase 1 saloon. The original lens is cracked. Reference number…"
                help="Include the side, reference number or measurements. Minimum 10 characters."
              />
              <p className="character-count">
                {description.length.toLocaleString()} / 5,000
              </p>
              <FormChoice
                name="car_id"
                label="Car profile (optional)"
                value={car}
                onValueChange={(v) => {
                  setCar(v);
                  invalidateVehicle();
                }}
                options={[
                  { value: "", label: "Enter vehicle details manually" },
                  ...d.cars.map((c) => ({ value: c.id, label: c.name })),
                ]}
              />
              {!car && (
                <Field
                  name="vehicle"
                  label="Vehicle name"
                  maxLength={120}
                  value={vehicle}
                  onChange={(e) => {
                    setVehicle(e.target.value);
                    invalidateVehicle();
                  }}
                  placeholder="Renault 19 Chamade, 1991"
                />
              )}
              {car && <input type="hidden" name="vehicle" value={vehicle} />}
              <p className="help">
                Saved vehicle specifications are included in every search.{" "}
                <a href="/cars/new">Add a car</a>
              </p>
            </Section>
            <Section
              title="Reference photos"
              description="Show the shape, mounting points or markings."
            >
              {(draft ? draft.photos : d.photos || []).length > 0 && (
                <div className="photo-grid">
                  {(draft
                    ? draft.photos
                    : (d.photos || []).map((p) => ({
                        ...p,
                        url: `/photos/${p.id}`,
                      }))
                  ).map((p, i) => (
                    <div key={p.id}>
                      <Photo
                        src={p.url}
                        alt={`Saved reference photo ${i + 1}`}
                      />
                      <CheckField
                        label={`Remove photo ${i + 1}`}
                        name={draft ? "remove_draft_photos" : "remove_photos"}
                        value={p.id}
                        defaultChecked={!draft && d.removed?.includes(p.id)}
                        onCheckedChange={changed}
                      />
                    </div>
                  ))}
                </div>
              )}
              <UploadPhotos resetKey={resetKey} />
            </Section>
            <Section
              title="Part details"
              description="References, measurements and alternate names help narrow the search."
            >
              {d.part_groups.map((group) => (
                <details
                  className="part-group"
                  key={group}
                  open={
                    group === "References" ||
                    facts.some(
                      (f) =>
                        f.review_status === "pending" &&
                        d.part_fields.find((x) => x[0] === f.field)?.[2] ===
                          group,
                    )
                  }
                >
                  <summary>{group}</summary>
                  <div className="pt-5">
                    {d.part_fields
                      .filter((f) => f[2] === group)
                      .map(([key, label, , multiple]) => {
                        const values = facts.filter((f) => f.field === key);
                        return (
                          <div key={key} className="fact-field">
                            {values.length ? (
                              values.map((f, i) =>
                                renderFact(
                                  f,
                                  label + (i ? " " + (i + 1) : ""),
                                  multiple,
                                ),
                              )
                            ) : (
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                  setFacts((current) => [
                                    ...current,
                                    newFact(key),
                                  ]);
                                  changed();
                                }}
                              >
                                Add {label.toLowerCase()}
                              </Button>
                            )}
                            {multiple && values.length > 0 && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                disabled={values.length >= 30}
                                onClick={() => {
                                  setFacts((current) => [
                                    ...current,
                                    newFact(key),
                                  ]);
                                  changed();
                                }}
                              >
                                <Plus size={14} />
                                Add another
                              </Button>
                            )}
                            {key === "references" && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={!!run}
                                onClick={() => start("identifiers")}
                              >
                                <Search size={14} />
                                Research exact identifiers
                              </Button>
                            )}
                          </div>
                        );
                      })}
                  </div>
                </details>
              ))}
            </Section>
          </fieldset>
          <Section
            title="Fill the gaps"
            description="Let AI suggest missing details. You review every suggestion."
            action={<Sparkles size={20} />}
          >
            <div className="field-grid">
              <FormChoice
                label="AI connection & model"
                value={model}
                disabled={busy || !!run}
                onValueChange={(v) => {
                  setModel(v);
                  setEffort("");
                }}
                options={[
                  { value: "codex:", label: "Codex · account default" },
                  ...Object.keys(d.part_codex_models).map((m) => ({
                    value: "codex:" + m,
                    label: "Codex · " + m,
                  })),
                  ...d.part_models.map((m) => ({
                    value: "openwebui:" + m,
                    label: "Open WebUI · " + m,
                  })),
                ]}
              />
              <FormChoice
                label="Reasoning effort"
                value={effort}
                disabled={busy || !!run}
                onValueChange={setEffort}
                options={[
                  { value: "", label: "Model default" },
                  ...(d.part_codex_models[model.slice(6)] || []).map((v) => ({
                    value: v,
                    label: v,
                  })),
                ]}
              />
            </div>
            <CheckField
              label="Include part photos (requires vision support)"
              checked={includePhotos}
              onCheckedChange={setIncludePhotos}
              disabled={busy || !!run}
            />
            <p className="help my-4">
              AI response:{" "}
              {d.language_names[d.language_preferences.response_language]} ·
              Search languages:{" "}
              {d.language_preferences.search_languages
                .map((c) => d.language_names[c])
                .join(", ")}
              . <a href="/settings">Language preferences</a>
            </p>
            <p className="help mb-4">
              Sends the description, part details and vehicle specifications to
              your provider. May use account credits. Codex can research
              sources; Open WebUI profile fill uses model knowledge.
            </p>
            <div className="actions">
              <Button
                type="button"
                variant="outline"
                disabled={busy || !!run}
                onClick={() => start("profile")}
              >
                <Sparkles size={16} />
                Fill with AI
              </Button>
              {run && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      const id = run;
                      cancelledRun.current = id;
                      setRun(null);
                      try {
                        const result = await requestData<{ message: string }>(
                          `/part-drafts/${draft!.id}/enrichments/${id}/cancel`,
                          minimal(),
                        );
                        setMessage(result.message);
                      } catch (e) {
                        cancelledRun.current = null;
                        setRun(id);
                        throw e;
                      }
                    })
                  }
                >
                  Cancel AI fill
                </Button>
              )}
              {review.undo.length > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    setFacts((current) => undoFill(current, review.undo));
                    setReview((r) => ({ ...r, pending: [], undo: [] }));
                    changed();
                    setMessage("AI fill undone. Later edits are preserved.");
                  }}
                >
                  <Undo2 size={15} />
                  Undo fill
                </Button>
              )}
            </div>
            {message && (
              <p className="fill-status" role="status">
                {message}
              </p>
            )}
            {notes.map((n, i) => (
              <p key={i} className="help mt-3">
                {n}
              </p>
            ))}
            {pending.length > 0 && (
              <div className="review-notice">
                <p>
                  {pending.length} suggestions need review. Accepting keeps them
                  unverified.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setFacts((current) =>
                      current.map((f) =>
                        f.review_status === "pending"
                          ? { ...f, review_status: "accepted" }
                          : f,
                      ),
                    );
                    changed();
                  }}
                >
                  Accept non-conflicting suggestions
                </Button>
              </div>
            )}
            {review.pending.map((f) => (
              <div className="review-notice" key={f.id}>
                <h3>
                  Alternative:{" "}
                  {d.part_fields.find((x) => x[0] === f.field)?.[1]}
                </h3>
                <p className="help">
                  Your value:{" "}
                  {facts
                    .filter((x) => x.field === f.field && x.value)
                    .map((x) => x.value)
                    .join("; ") || "Empty"}
                </p>
                <p>AI suggests: {f.value}</p>
                {f.reason && <p className="help">{f.reason}</p>}
                <div className="actions">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const previous = facts.filter((x) => x.field === f.field);
                      const multiple = d.part_fields.find(
                        (x) => x[0] === f.field,
                      )?.[3];
                      setFacts((current) => [
                        ...current.filter(
                          (x) => multiple || x.field !== f.field,
                        ),
                        { ...f, review_status: "accepted" },
                      ]);
                      setReview((r) => ({
                        ...r,
                        pending: r.pending.filter((x) => x.id !== f.id),
                        undo: [
                          ...r.undo,
                          {
                            id: f.id,
                            value: f.value,
                            previous: multiple ? [] : previous,
                          },
                        ],
                      }));
                      changed();
                    }}
                  >
                    Use suggestion
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => dismiss(f)}
                  >
                    Keep my value
                  </Button>
                </div>
              </div>
            ))}
          </Section>
          <div className="form-actions">
            <Button type="submit" disabled={busy || !!run}>
              <Check size={16} />
              {busy
                ? "Saving…"
                : d.order
                  ? "Save changes"
                  : "Create part request"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  await saveDraft();
                  setMessage(
                    "Draft saved for seven days in this browser session.",
                  );
                })
              }
            >
              <Save size={15} />
              Save draft
            </Button>
            <LinkButton
              href={d.order ? `/requests/${d.order.id}` : "/"}
              variant="ghost"
            >
              Cancel
            </LinkButton>
          </div>
          <p className="help">Saving a part request does not start a search.</p>
        </form>
        <aside className="form-aside">
          <FileText size={26} />
          <h2>A good brief goes a long way</h2>
          <p>
            Start with the part’s name, which side it fits, and what makes your
            version different.
          </p>
          <p>
            A photo of a stamped reference or connector can be more useful than
            a long description.
          </p>
          <div className="aside-divider" />
          <Sparkles size={22} />
          <h3>Unsure of a detail?</h3>
          <p>
            Leave it blank. AI can suggest missing information for you to
            review.
          </p>
        </aside>
      </div>
    </>
  );
}
