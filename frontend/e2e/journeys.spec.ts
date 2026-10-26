import {test,expect, type Page} from "@playwright/test";

async function login(page:Page,email="central@casesync.demo"){
  await page.goto("/");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill("CaseSync@2026");
  await page.getByRole("button",{name:"Secure sign in"}).click();
  await expect(page.getByText("Complaint command overview")).toBeVisible({timeout:30_000});
}

test("central administrator can navigate the live operational journeys",async({page})=>{
  await login(page);
  await page.getByRole("button",{name:"Institutions"}).click();
  await expect(page.getByText("Institution registry")).toBeVisible();
  await page.getByRole("button",{name:"Complaints"}).click();
  await expect(page.getByText("Register complaint")).toBeVisible();
  await page.getByRole("button",{name:"Overlap Intelligence"}).click();
  await expect(page.getByText("Overlap intelligence")).toBeVisible();
  await page.getByRole("button",{name:"Reports & Analytics"}).click();
  await expect(page.getByRole("button",{name:/CSV/})).toBeEnabled();
});

test("auditor receives read-only navigation",async({page})=>{
  await login(page,"auditor@casesync.demo");
  await page.getByRole("button",{name:"Complaints"}).click();
  await expect(page.getByRole("button",{name:"Register complaint"})).toHaveCount(0);
});

test("authorized official registers a complaint through the live UI",async({page})=>{
  test.setTimeout(120_000);
  await login(page);
  await page.getByRole("button",{name:"Complaints"}).click();
  await page.getByRole("button",{name:"Register complaint"}).click();
  const modal=page.locator(".modal");
  const inputs=modal.locator("input");
  await inputs.nth(1).fill(`Synthetic E2E fee complaint ${Date.now()}`);
  await modal.locator("textarea").fill("Students reported a synthetic unapproved additional fee for end-to-end overlap workflow validation.");
  const selects=modal.locator("select");
  await selects.nth(0).selectOption({index:1});
  await selects.nth(1).selectOption({index:1});
  await selects.nth(2).selectOption("high");
  await selects.nth(3).selectOption({index:1});
  await page.getByRole("button",{name:"Register complaint",exact:true}).last().click();
  await expect(page.getByText("Complaint record")).toBeVisible({timeout:90_000});
  await expect(page.getByText(/CMP-2026-/).first()).toBeVisible();
});

test("central administrator reviews explainable overlap and creates coordination",async({page})=>{
  await login(page);
  const response=await page.request.get("http://localhost:8000/api/v1/overlaps?state=pending&page_size=1");
  const finding=(await response.json()).items[0];
  expect(finding).toBeTruthy();
  await page.goto(`/overlaps/${finding.id}`);
  await expect(page.getByText("AI-assisted evidence")).toBeVisible();
  await page.getByRole("button",{name:"Confirmed"}).click();
  await page.locator(".modal textarea").fill("Confirmed by the synthetic Playwright coordination journey.");
  await page.getByRole("button",{name:"Record decision"}).click();
  await expect(page.getByText(/Review outcome:/)).toBeVisible();
  await page.getByRole("button",{name:"Coordination Center"}).click();
  await expect(page.getByText("Coordination center")).toBeVisible();
});

test("transfer is recorded and accepted through the complaint workflow",async({page})=>{
  await login(page);
  const response=await page.request.get("http://localhost:8000/api/v1/complaints?status=pending&page_size=1");
  const complaint=(await response.json()).items[0];
  await page.goto(`/complaints/${complaint.id}`);
  await page.getByRole("button",{name:"Transfer",exact:true}).click();
  const modal=page.locator(".modal");
  await modal.locator("textarea").fill("Transfer requested by the synthetic end-to-end workflow.");
  await modal.locator("select").selectOption({index:1});
  await page.getByRole("button",{name:"Confirm action"}).click();
  await expect(page.getByRole("button",{name:"Accept Transfer"})).toBeVisible();
  await page.getByRole("button",{name:"Accept Transfer"}).click();
  await page.locator(".modal textarea").fill("Transfer accepted by the receiving synthetic workflow.");
  await page.getByRole("button",{name:"Confirm action"}).click();
  await expect(page.getByText("Under Process").first()).toBeVisible();
});

test("system administrator manages configuration and runs SLA notifications",async({page})=>{
  await login(page,"admin@casesync.demo");
  await page.getByRole("button",{name:"User & Bureau Management"}).click();
  await expect(page.getByRole("button",{name:"User",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Settings",exact:true}).click();
  await expect(page.getByText("Overlap engine")).toBeVisible();
  await page.getByRole("button",{name:"Save thresholds"}).click();
  await expect(page.getByText(/thresholds saved/i)).toBeVisible();
  await page.getByRole("button",{name:"Run SLA scan"}).click();
  await expect(page.getByText(/SLA scan completed/)).toBeVisible();
  await page.getByRole("button",{name:"Alerts & Notifications"}).click();
  await expect(page.getByText("Alerts & notifications")).toBeVisible();
});


