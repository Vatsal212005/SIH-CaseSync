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
  await expect(page.getByText("Watch CaseSync reason, decide and coordinate")).toBeVisible();
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

test("interactive demo shows computed restraint for different complaints", async ({page}) => {
  test.setTimeout(180_000);
  await login(page);
  await page.locator(".nav").getByRole("button", {name: "Interactive Demo"}).click();
  const scenario = page.locator(".scenario-card").filter({hasText: "Same institution, different complaints"});
  await scenario.getByRole("button", {name: "Start isolated demo"}).click();
  await expect(page.getByText("Live system state")).toBeVisible();

  for (const action of [
    "Register canonical institution",
    "Receive fee complaint",
    "Receive infrastructure complaint",
    "Run AI distinction analysis",
    "Explain the computed outcome",
  ]) {
    const run = page.getByRole("button", {name: `Run: ${action}`});
    await expect(run).toBeEnabled({timeout: 90_000});
    await run.click();
  }

  await expect(page.getByText("Same institution did not become an automatic duplicate")).toBeVisible({timeout: 90_000});
  await expect(page.getByText("Evidence evaluated; no automatic coordination")).toBeVisible();
  expect(await page.locator(".demo-live-state button").count()).toBeGreaterThanOrEqual(6);
});

test("duplicate investigation demo requires human review before coordination", async ({page}) => {
  test.setTimeout(240_000);
  await login(page);
  await page.locator(".nav").getByRole("button", {name: "Interactive Demo"}).click();
  const scenario = page.locator(".scenario-card").filter({hasText: "AI detects duplicate investigations"});
  await scenario.getByRole("button", {name: "Start isolated demo"}).click();

  for (const action of [
    "Register canonical institution",
    "Receive PGRC complaint",
    "Receive Regulation Bureau complaint",
    "Run AI overlap analysis",
  ]) {
    const run = page.getByRole("button", {name: `Run: ${action}`});
    await expect(run).toBeEnabled({timeout: 90_000});
    await run.click();
  }

  await expect(page.getByText("The AI has proposed a candidate relationship. An authorized official must decide.")).toBeVisible({timeout: 90_000});
  await expect(page.getByText("Semantic similarity", {exact: true}).first()).toBeVisible();
  await page.getByRole("button", {name: "Record explicit human decision"}).click();
  await expect(page.getByRole("button", {name: "Create accountable coordination"})).toBeVisible({timeout: 30_000});
  await page.getByRole("button", {name: "Create accountable coordination"}).click();
  await expect(page.getByText("Evidence reviewed and coordination established")).toBeVisible({timeout: 30_000});
  await expect(page.getByRole("button", {name: "View Coordination Center"})).toBeVisible();
});

test("SLA demo persists assignment, notification evidence and escalation", async ({page}) => {
  test.setTimeout(180_000);
  await login(page);
  await page.locator(".nav").getByRole("button", {name: "Interactive Demo"}).click();
  const scenario = page.locator(".scenario-card").filter({hasText: "SLA violation and escalation"});
  await scenario.getByRole("button", {name: "Start isolated demo"}).click();

  for (const action of [
    "Register canonical institution",
    "Receive deadline-sensitive complaint",
    "Assign an accountable officer",
    "Run SLA monitoring",
    "Escalate the complaint",
  ]) {
    const run = page.getByRole("button", {name: `Run: ${action}`});
    await expect(run).toBeEnabled({timeout: 90_000});
    await run.click();
  }

  await expect(page.getByText("Deadline risk became accountable action")).toBeVisible({timeout: 30_000});
  await expect(page.getByText("Status: Escalated")).toBeVisible();
  await expect(page.getByRole("button", {name: "View Notifications"})).toBeVisible();
});

test("active demo session recovers after refresh", async ({page}) => {
  await login(page);
  await page.locator(".nav").getByRole("button", {name: "Interactive Demo"}).click();
  const scenario = page.locator(".scenario-card").filter({hasText: "Same institution, different complaints"});
  await scenario.getByRole("button", {name: "Start isolated demo"}).click();
  await page.getByRole("button", {name: "Run: Register canonical institution"}).click();
  await page.reload();
  await page.getByRole("button", {name: /Continue current session/}).click();
  await page.getByRole("button", {name: /Institution registered/}).click();
  await expect(page.getByText("Synthetic institution profile")).toBeVisible();
});

test("frontend falls back to a clearly labeled preset demo when the API is offline", async ({page}) => {
  await page.route("**/api/v1/**", route => route.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByText("OFFLINE FRONTEND PREVIEW", {exact: false})).toBeVisible({timeout: 10_000});
  await expect(page.getByText("Offline preset preview", {exact: true})).toBeVisible();

  const scenario = page.locator(".scenario-card").filter({hasText: "AI detects duplicate investigations"});
  await scenario.getByRole("button", {name: "Start preset demo"}).click();
  for (const action of [
    "Register canonical institution",
    "Receive PGRC complaint",
    "Receive Regulation Bureau complaint",
    "Run AI overlap analysis",
  ]) {
    await page.getByRole("button", {name: `Run: ${action}`}).click();
  }
  await page.getByRole("button", {name: "Record explicit human decision"}).click();
  await page.getByRole("button", {name: "Create accountable coordination"}).click();
  await expect(page.getByText("Evidence reviewed and coordination established")).toBeVisible();
  await expect(page.getByText("no backend persistence or live inference", {exact: false})).toBeVisible();
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
