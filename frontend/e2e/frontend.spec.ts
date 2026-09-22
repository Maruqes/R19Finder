import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const order = "/requests/22222222-2222-4222-8222-222222222222";
const car = "/cars/11111111-1111-4111-8111-111111111111";
test("all routes render at desktop and mobile widths without runtime errors or overflow", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("404"))
      errors.push(m.text());
  });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of [
      "/",
      "/cars",
      "/cars/new",
      "/requests/new",
      "/websites",
      "/ai",
      "/discord",
      "/settings",
      order,
      order + "/edit",
      car,
      car + "/edit",
    ]) {
      await page.goto(route);
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.getByText("This page couldn’t load")).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  expect(errors).toEqual([]);
});
test("keyboard selection, mobile navigation and focus obey CSP", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto("/requests/new");
  const trigger = page.getByRole("combobox", {
    name: "Car profile (optional)",
  });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await page
    .getByRole("option", { name: "Test Renault 19", exact: true })
    .click();
  await expect(page.getByLabel("Vehicle name")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeFocused();
  expect(errors).toEqual([]);
});
test("request draft, photo upload, recovery, commit and edit use the real API", async ({
  page,
}) => {
  await page.goto("/requests/new");
  await page
    .getByRole("textbox", { name: "Description *", exact: true })
    .fill("Browser test alternator with mounting bracket");
  await page.getByLabel("Vehicle name").fill("Renault 19, 1991");
  await page.getByLabel("Choose reference photos").setInputFiles({
    name: "photo.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Draft saved" }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Resume draft" }).click();
  await expect(
    page.getByRole("textbox", { name: "Description *", exact: true }),
  ).toHaveValue("Browser test alternator with mounting bracket");
  await expect(
    page.getByRole("img", { name: "Saved reference photo 1" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create part request", exact: true })
    .click();
  await expect(page).toHaveURL(/\/requests\/[a-f0-9-]+$/);
  await page.getByRole("link", { name: "Edit request" }).click();
  await page
    .getByRole("textbox", { name: "Description *", exact: true })
    .fill("Updated alternator with matching mounting bracket");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page).toHaveURL(/\/requests\/[a-f0-9-]+$/);
  await expect(
    page.getByText("Updated alternator with matching mounting bracket", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Part reference photo 1" }),
  ).toBeVisible();
});
test("history renders safe markdown and incomplete legacy metadata", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(order);
  await page.getByRole("tab", { name: "History" }).click();
  await page.getByText("View search report", { exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "Possible match" }),
  ).toBeVisible();
  expect(await page.evaluate(() => "unsafeExecuted" in window)).toBe(false);
  await expect(
    page.getByText("No evidence of web search was returned.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Sources", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("schedule creation, pause, notification preference and confirmed deletion", async ({
  page,
}) => {
  await page.goto(order);
  await page.getByRole("tab", { name: "New search", exact: true }).click();
  await page.getByText("Create a weekly schedule", { exact: true }).click();
  await page.getByLabel("Monday", { exact: true }).check();
  await page.getByRole("button", { name: "Save weekly schedule" }).click();
  await page.getByRole("tab", { name: "Schedules" }).click();
  await expect(
    page.getByRole("heading", { name: "Monday · 16:30" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause schedule" }).click();
  await page.getByRole("tab", { name: "Schedules" }).click();
  await expect(
    page.getByRole("button", { name: "Enable schedule" }),
  ).toBeVisible();
  await page.getByLabel("Discord notifications", { exact: true }).check();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByRole("tab", { name: "Schedules" }).click();
  await expect(
    page.getByLabel("Discord notifications", { exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Keep schedule" }).click();
  await expect(
    page.getByRole("heading", { name: "Monday · 16:30" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page
    .getByRole("button", { name: "Delete schedule", exact: true })
    .click();
  await page.getByRole("tab", { name: "Schedules" }).click();
  await expect(page.getByText("No scheduled searches")).toBeVisible();
});
test("listing blacklist can be reversed and settings validate submitted values", async ({
  page,
}) => {
  await page.goto(order);
  await page.getByText("Remove & blacklist", { exact: true }).click();
  await page.getByLabel("Reason (optional)").fill("Wrong mounting points");
  await page.getByRole("button", { name: "Confirm removal" }).click();
  await expect(page.getByText("No listings found yet")).toBeVisible();
  await page.getByText("Blacklist · 1 hidden listing").click();
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Original left tail light",
      exact: true,
    }),
  ).toBeVisible();
  await page.goto("/websites");
  await page
    .getByLabel("Websites, in priority order")
    .fill("https://example.com\nhttps://example.org");
  await page.getByRole("button", { name: "Save websites" }).click();
  await expect(page.getByLabel("Websites, in priority order")).toHaveValue(
    "https://example.com\nhttps://example.org",
  );
  await page.goto("/settings");
  await page.getByRole("combobox", { name: "Response language" }).click();
  await page.getByRole("option", { name: "Português", exact: true }).click();
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(
    page.getByRole("combobox", { name: "Response language" }),
  ).toContainText("Português");
});
test("main screens pass the automated WCAG A/AA checks", async ({ page }) => {
  for (const route of ["/", "/requests/new", "/settings", order]) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      audit.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
      route,
    ).toEqual([]);
  }
});
test("AI suggestions preserve edits made during research and require review", async ({
  page,
}) => {
  let input: Record<string, unknown>;
  let release: () => void = () => {};
  const completion = new Promise<void>((resolve) => {
    release = resolve;
  });
  page.on("response", async (r) => {
    if (r.url().endsWith("/part-drafts") && r.status() === 201)
      input = (await r.json()).content;
  });
  await page.route("**/part-drafts/*/enrichments", (r) =>
    r.fulfill({ json: { id: "33333333-3333-4333-8333-333333333333" } }),
  );
  await page.route("**/part-drafts/*/enrichments/*", async (r) => {
    await completion;
    await r.fulfill({
      json: {
        id: "33333333-3333-4333-8333-333333333333",
        status: "completed",
        input,
        output: {
          suggestions: [
            {
              id: "44444444-4444-4444-8444-444444444444",
              field: "name",
              value: "AI suggested lamp",
              origin: "ai",
              review_status: "pending",
              verification_status: "unverified",
            },
          ],
        },
      },
    });
  });
  await page.goto("/requests/new");
  await page
    .getByRole("textbox", { name: "Description *", exact: true })
    .fill("A lamp with damaged lens and original studs");
  await page.getByRole("button", { name: "Fill with AI", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Cancel AI fill" }),
  ).toBeVisible();
  await page.getByText("Identification", { exact: true }).click();
  await page
    .getByLabel("Part name", { exact: true })
    .fill("My manually identified lamp");
  release();
  await expect(page.getByText("AI suggests: AI suggested lamp")).toBeVisible();
  await expect(page.getByLabel("Part name", { exact: true })).toHaveValue(
    "My manually identified lamp",
  );
  await page
    .getByRole("button", { name: "Create part request", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Review all highlighted suggestions",
  );
  await page.getByRole("button", { name: "Keep my value" }).click();
  await page
    .getByRole("button", { name: "Create part request", exact: true })
    .click();
  await expect(page).toHaveURL(/\/requests\/[a-f0-9-]+$/);
  await expect(page.locator("h1")).toHaveText("My manually identified lamp");
});

test("invalid draft responses show an error and preserve entered text", async ({
  page,
}) => {
  await page.route("**/part-drafts", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<html>Proxy error</html>",
    }),
  );
  await page.goto("/requests/new");
  const description = page.getByRole("textbox", {
    name: "Description *",
    exact: true,
  });
  await description.fill("Rear drum brake assembly");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("invalid response");
  await expect(description).toHaveValue("Rear drum brake assembly");
  await expect(page).toHaveURL(/\/requests\/new$/);
});
