import {expect, test, type Page} from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email address").fill("central@casesync.demo");
  await page.getByLabel("Password").fill("CaseSync@2026");
  await page.getByRole("button", {name: "Secure sign in"}).click();
  await expect(page.getByText("Complaint command overview")).toBeVisible({timeout: 30_000});
}

test("enhanced primary views emit no critical browser errors", async ({page}) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    if (message.type() === "error" && !message.text().includes("401")) errors.push(message.text());
  });
  await login(page);
  await page.locator(".nav").getByRole("button", {name: "Interactive Demo"}).click();
  await expect(page.getByText("See CaseSync solve the coordination problem")).toBeVisible();
  await page.locator(".nav").getByRole("button", {name: "Reports & Analytics"}).click();
  await expect(page.getByRole("button", {name: /CSV/})).toBeEnabled();
  expect(errors).toEqual([]);
});

test("guided tour targets working navigation and persists completion", async ({page}) => {
  await login(page);
  await page.getByRole("button", {name: "Take a Tour"}).click();
  await expect(page.getByText("Product tour · 1 of 8")).toBeVisible();
  await page.getByRole("button", {name: "Next", exact: true}).click();
  await expect(page.getByText("Product tour · 2 of 8")).toBeVisible();
  await expect(page.getByText("Institution registry")).toBeVisible();
  await page.getByRole("button", {name: "Back"}).click();
  await expect(page.getByText("Product tour · 1 of 8")).toBeVisible();
  await page.getByRole("button", {name: "Skip"}).click();
  await expect(page.getByRole("dialog", {name: "CaseSync product tour"})).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("casesync-tour-complete"))).toBe("true");
});

test("interactive demo runs the real same-institution comparison workflow", async ({page}) => {
  test.setTimeout(180_000);
  await login(page);
  await page.locator(".nav").getByRole("button", {name: "Interactive Demo"}).click();
  const scenario = page.locator(".scenario-card").filter({hasText: "Same institution, different complaints"});
  await scenario.getByRole("button", {name: "Start demo"}).click();
  await expect(page.getByText("Live services")).toBeVisible();

  for (let step = 0; step < 4; step += 1) {
    const run = page.getByRole("button", {name: /^Run:/});
    await expect(run).toBeEnabled({timeout: 90_000});
    const eventsBefore = await page.locator(".demo-event").count();
    await run.click();
    await expect(page.locator(".demo-event")).toHaveCount(eventsBefore + 1, {timeout: 90_000});
  }

  await expect(page.getByText("Scenario completed")).toBeVisible({timeout: 90_000});
  await expect(page.getByText("Same-institution evaluation completed")).toBeVisible();
  await expect(page.getByText("The engine distinguishes shared institutional activity from semantic duplication.")).toBeVisible();
  expect(await page.locator(".live-records button").count()).toBeGreaterThanOrEqual(2);
});

test("AI comparison coordinates cases and exposes their real journey", async ({page}) => {
  test.setTimeout(180_000);
  await login(page);
  const response = await page.request.get("http://localhost:8000/api/v1/overlaps?state=pending&page_size=20");
  const finding = (await response.json()).items.find((row: {complaint_a: {assigned_bureau: {id: string}}; complaint_b: {assigned_bureau: {id: string}}}) =>
    row.complaint_a.assigned_bureau.id !== row.complaint_b.assigned_bureau.id,
  );
  expect(finding).toBeTruthy();

  await page.goto(`/overlaps/${finding.id}`);
  await expect(page.getByText("AI Case Comparison")).toBeVisible();
  await expect(page.getByText("Complaint A")).toBeVisible();
  await expect(page.getByText("Complaint B")).toBeVisible();
  await expect(page.getByText("Semantic similarity", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: "Coordinate Cases"}).click();
  await page.getByRole("button", {name: /Assign responsibility/}).click();
  await page.getByRole("button", {name: /Review summary/}).click();
  await page.getByRole("button", {name: "Confirm coordination"}).click();
  await expect(page.getByText("Coordination workspace ready")).toBeVisible({timeout: 30_000});

  await page.goto(`/complaints/${finding.complaint_a.id}`);
  await expect(page.getByText("Case Journey")).toBeVisible();
  await expect(page.getByText("Coordination Started", {exact: true}).first()).toBeVisible();
  await page.goto(`/institutions/${finding.complaint_a.institution.id}`);
  await expect(page.getByText("Institution intelligence overview")).toBeVisible();
  await expect(page.getByText("Complaint volume over time")).toBeVisible();
});
