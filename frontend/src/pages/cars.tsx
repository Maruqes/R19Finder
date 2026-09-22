import { useState } from "react";
import { CarFront, Plus, Search, SquarePen } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Back,
  CheckField,
  Empty,
  Field,
  FormChoice,
  Gallery,
  Heading,
  LinkButton,
  Notice,
  Photo,
  PostForm,
  Section,
  UploadPhotos,
} from "@/components/shared";
import { usePage } from "@/lib/page";
import type { Car, Order, Spec } from "@/lib/types";
import { CarCard, RequestRows } from "./dashboard";
export function Cars() {
  const { data } = usePage<{ cars: Car[] }>();
  const [q, setQ] = useState("");
  const cars = data.cars.filter((c) =>
    `${c.name} ${Object.values(c.specs).join(" ")}`
      .toLowerCase()
      .includes(q.toLowerCase()),
  );
  return (
    <>
      <Heading
        title="Your garage"
        description="Save vehicle specifications for your part searches."
        action={
          <LinkButton href="/cars/new">
            <Plus size={16} />
            Add car
          </LinkButton>
        }
      />
      <div className="garage-toolbar">
        <p className="help">
          {data.cars.length} {data.cars.length === 1 ? "car" : "cars"} in your
          garage
        </p>
        <div className="search-input">
          <Search size={17} />
          <Input
            aria-label="Find a car"
            placeholder="Find a car…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      {cars.length ? (
        <div className="car-grid">
          {cars.map((car) => (
            <CarCard key={car.id} car={car} />
          ))}
        </div>
      ) : (
        <Empty
          icon={CarFront}
          title={q ? "No matching cars" : "Your garage starts here"}
          description={
            q
              ? "Try a different name, make or model."
              : "Save a vehicle profile so every search includes the details that matter."
          }
          action={
            <LinkButton href="/cars/new">
              <Plus size={16} />
              Add car
            </LinkButton>
          }
        />
      )}
    </>
  );
}
export function CarForm() {
  const { data: d } = usePage<{
    car?: Car;
    values: Record<string, string>;
    fields: Spec[];
    error?: string;
  }>();
  const main = ["make", "model", "year", "body_style"];
  function spec([key, label, placeholder]: Spec) {
    return key === "abs" ? (
      <FormChoice
        key={key}
        name={key}
        label={label}
        defaultValue={d.values[key] || ""}
        options={["", "Yes", "No"].map((v) => ({
          value: v,
          label: v || "Unknown",
        }))}
      />
    ) : (
      <Field
        key={key}
        name={key}
        label={label}
        required={["make", "model"].includes(key)}
        defaultValue={d.values[key] || ""}
        placeholder={placeholder}
        maxLength={120}
        {...(key === "year"
          ? { inputMode: "numeric", pattern: "[0-9]{4}" }
          : {})}
      />
    );
  }
  return (
    <>
      <Back href={d.car ? `/cars/${d.car.id}` : "/cars"}>
        {d.car?.name || "Your garage"}
      </Back>
      <Heading
        title={d.car ? "Edit car" : "Add a car"}
        description="A few details now. More accurate part searches later."
      />
      <div className="form-layout">
        <PostForm encType="multipart/form-data" className="form-main">
          {d.error && <Notice error>{d.error} Select new photos again.</Notice>}
          <Section
            title="Vehicle profile"
            description="Profile name, make and model are required."
          >
            <Field
              label="Profile name"
              name="name"
              required
              defaultValue={d.values.name || ""}
              maxLength={120}
              placeholder="My Renault 19 Chamade"
            />
            <div className="field-grid">
              {d.fields.filter((f) => main.includes(f[0])).map(spec)}
            </div>
          </Section>
          <Section
            title="Car photos"
            description="Keep a visual record of your vehicle."
          >
            {!!d.car?.photo_ids?.length && (
              <div className="photo-grid">
                {d.car.photo_ids.map((p, i) => (
                  <div key={p}>
                    <Photo
                      src={`/cars/${d.car!.id}/photos/${p}`}
                      alt={`Current car photo ${i + 1}`}
                    />
                    <CheckField
                      name="remove_photos"
                      value={p}
                      label={`Remove photo ${i + 1}`}
                    />
                  </div>
                ))}
              </div>
            )}
            <UploadPhotos car />
          </Section>
          <Section>
            <details open={!!d.car}>
              <summary>
                Technical specifications <span className="help">Optional</span>
              </summary>
              <p className="help mt-3 mb-5">
                Leave unknown details blank. Saved specifications are included
                in future searches.
              </p>
              <div className="field-grid">
                {d.fields.filter((f) => !main.includes(f[0])).map(spec)}
              </div>
            </details>
          </Section>
          <Section title="Notes & modifications">
            <Field
              label="Technical notes"
              name="notes"
              textarea
              rows={4}
              maxLength={3000}
              defaultValue={d.values.notes || ""}
              placeholder="Modifications, mounting measurements, known references…"
              help="Include useful technical details. Avoid personal information."
            />
          </Section>
          <div className="form-actions">
            <Button type="submit">Save car</Button>
            <LinkButton
              variant="ghost"
              href={d.car ? `/cars/${d.car.id}` : "/cars"}
            >
              Cancel
            </LinkButton>
          </div>
        </PostForm>
        <aside className="form-aside">
          <CarFront size={26} />
          <h2>Vehicle details</h2>
          <p>
            Engine codes, model years and body styles help distinguish parts
            that look alike.
          </p>
          <p>You can fill in more details any time.</p>
        </aside>
      </div>
    </>
  );
}
export function CarDetail() {
  const {
    data: { car, fields, orders },
  } = usePage<{ car: Car; fields: Spec[]; orders: Order[] }>();
  return (
    <>
      <Back href="/cars">Your garage</Back>
      <Heading
        title={car.name}
        description={[car.specs.make, car.specs.model, car.specs.year]
          .filter(Boolean)
          .join(" · ")}
        action={
          <div className="actions">
            <LinkButton variant="outline" href={`/cars/${car.id}/edit`}>
              <SquarePen size={16} />
              Edit car
            </LinkButton>
            <LinkButton href={`/requests/new?car_id=${car.id}`}>
              <Plus size={16} />
              New part request
            </LinkButton>
          </div>
        }
      />
      <div className="detail-grid">
        <div>
          <Gallery
            name={car.name}
            photos={(car.photo_ids || []).map(
              (p) => `/cars/${car.id}/photos/${p}`,
            )}
          />
          <Section title="Vehicle specifications" className="mt-6">
            <dl className="spec-grid">
              {fields.map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{car.specs[key] || "Not specified"}</dd>
                </div>
              ))}
            </dl>
          </Section>
          <Section title="Notes & modifications" className="mt-6">
            <p className="prose-copy">{car.specs.notes || "No notes added."}</p>
          </Section>
        </div>
        <section>
          <div className="section-heading">
            <h2>
              Part requests <span className="count">{orders.length}</span>
            </h2>
          </div>
          {orders.length ? (
            <RequestRows orders={orders} />
          ) : (
            <Empty
              title="No requests for this car yet"
              description="Link a part request to this vehicle to include its specifications in your research."
              action={
                <LinkButton href={`/requests/new?car_id=${car.id}`}>
                  New part request
                </LinkButton>
              }
            />
          )}
        </section>
      </div>
    </>
  );
}
