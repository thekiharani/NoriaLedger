import { expect, type Page, test } from "@playwright/test";

const password = process.env.NORIA_DEMO_PASSWORD ?? "";
const shots = process.env.NORIA_SCREENSHOT_DIR;

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

test.beforeAll(() => {
  if (!password) throw new Error("NORIA_DEMO_PASSWORD is required");
});

test("firm admin sees dashboard, client books and reports", async ({ page }) => {
  await login(page, "amina@wanjiru.demo");
  await expect(page.getByText("Active clients")).toBeVisible();
  await shot(page, "01-dashboard");

  await page.getByRole("link", { name: "Clients" }).click();
  await expect(page.getByText("Savanna Coffee Roasters Ltd")).toBeVisible();
  await shot(page, "02-clients");

  await page.getByText("Savanna Coffee Roasters Ltd").click();
  await expect(page.getByText("Cash & bank")).toBeVisible();
  await shot(page, "03-client-overview");

  await page.getByRole("tab", { name: "Journals" }).click();
  await expect(page.getByText("Opening capital introduced")).toBeVisible();

  await page.getByRole("tab", { name: "Banking" }).click();
  await expect(page.getByText("Bank transactions")).toBeVisible();
  await shot(page, "04-banking");

  await page.getByRole("tab", { name: "Reports", exact: true }).click();
  await page.getByLabel("Report", { exact: true }).selectOption("Profit and Loss Statement");
  await page.getByLabel("From", { exact: true }).fill("2026-09-01");
  await page.getByLabel("To", { exact: true }).fill("2026-09-30");
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.getByText("Total Income (Credit)").first()).toBeVisible();
  await shot(page, "05-profit-and-loss");
});

test("independent accountant cannot see another firm's client", async ({ page }) => {
  await login(page, "peter@otieno.demo");
  await page.getByRole("link", { name: "Clients" }).click();
  await expect(page.getByText("Mama Mboga Fresh Produce")).toBeVisible();
  await expect(page.getByText("Savanna Coffee Roasters Ltd")).toHaveCount(0);
  await page.goto("/clients/CLT-00001");
  await expect(page.getByText("Client not found or access denied")).toBeVisible();
});

test("client portal shows only published reports for own business", async ({ page }) => {
  await login(page, "owner@savanna.demo");
  await expect(page).toHaveURL(/\/portal/);
  await expect(page.getByText("Management accounts · 2026-09")).toBeVisible();
  await shot(page, "06-portal");
  await page.getByText("Management accounts · 2026-09").click();
  await expect(page.getByText("Net profit").first()).toBeVisible();
  await shot(page, "07-portal-report");
  await page.goto("/clients");
  await expect(page).toHaveURL(/\/portal/);
});
