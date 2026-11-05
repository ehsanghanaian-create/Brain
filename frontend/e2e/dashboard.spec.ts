import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const external = !!process.env.UI_QA_BASE_URL && !process.env.UI_QA_FIXTURE;
const site = external ? 'salimore' : 'qa-site';

test.beforeEach(async ({ page }) => {
  // All live smoke tests are read-only. Error states are mocked in the browser.
  await page.route('**/*', (route) =>
    ['GET', 'HEAD', 'OPTIONS'].includes(route.request().method()) ? route.continue() : route.abort()
  );
});

for (const width of [320, 375, 768, 1024, 1440]) {
  test(`overview is usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/dashboard/overview');
    await expect(page.getByRole('navigation', { name: 'مسیرهای اصلی رشد' })).toBeVisible();
    await expect(
      page.locator('header').getByRole('button', { name: 'کارهای پس‌زمینه', exact: true })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /رتبهٔ واقعی کلمات/ })).toHaveAttribute(
      'href',
      `/dashboard/rank-tracking?site=${site}`
    );
    await expect(page.getByLabel('تازگی داده‌های جست‌وجو')).toContainText('آخرین روز داده');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width
    );
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
          .analyze()
      ).violations
    ).toEqual([]);
  });
}

test('mobile navigation closes with Escape and returns focus', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/dashboard/overview');
  const trigger = page.getByRole('button', { name: 'باز و بسته کردن منو (Ctrl+B)' });
  await trigger.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('source failure is explained without claiming the data is fresh', async ({ page }) => {
  await page.route('**/gsc/sync/status', (route) =>
    route.fulfill({ status: 503, json: { error: { message: 'QA unavailable' } } })
  );
  await page.goto('/dashboard/overview');
  await expect(page.getByLabel('تازگی داده‌های جست‌وجو')).toContainText('دریافت وضعیت ناموفق بود');
});

test('graph relationships can be read and selected using the keyboard', async ({ page }) => {
  if (!external)
    await page.route('**/graph/view?**', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.nodes.push(
        { id: 'unrelated-page', site_id: site, type: 'PAGE', metadata: { label: 'صفحهٔ نامرتبط' } },
        { id: 'unrelated-query', site_id: site, type: 'QUERY', metadata: { label: 'پرسش نامرتبط' } }
      );
      data.edges.push({
        source: 'unrelated-page',
        target: 'unrelated-query',
        relation_type: 'RANKS_FOR',
        site_id: site,
        weight: 1,
        metadata: {}
      });
      data.total_nodes = 4;
      await route.fulfill({ response, json: data });
    });
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto(`/dashboard/graph?site=${site}`);
  await page.getByRole('button', { name: 'فهرست خوانای ارتباط‌ها', exact: true }).click();
  const list = page.getByRole('region', { name: 'فهرست ارتباط‌های گراف' });
  await expect(list).toBeVisible();
  await expect(list.getByText(/مبدأ ·/).first()).toBeVisible();
  await expect(list.getByText(/مقصد ·/).first()).toBeVisible();
  if (!external) {
    await expect(list.getByRole('button', { name: 'صفحهٔ نامرتبط' })).toHaveCount(0);
    await page.getByRole('button', { name: 'نمایش کل گراف', exact: true }).click();
    await expect(list.getByRole('button', { name: 'صفحهٔ نامرتبط' })).toBeVisible();
  }
  const node = list.getByRole('button').nth(1);
  const label = await node.innerText();
  await node.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: label, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'بستن جزئیات گره' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test('calendar failure has a retry instead of a misleading empty calendar', async ({ page }) => {
  let unavailable = true;
  await page.route('**/content-plans/calendar?**', (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { error: { message: 'QA unavailable' } } })
      : route.continue()
  );
  await page.goto(`/dashboard/calendar?site=${site}`);
  await expect(page.getByRole('alert', { name: 'خطای تقویم' })).toContainText(
    'به معنی خالی بودن تقویم نیست'
  );
  await expect(page.getByLabel('برنامهٔ روزانهٔ محتوا')).toHaveCount(0);
  unavailable = false;
  await page.getByRole('button', { name: 'تلاش دوباره' }).click();
  await expect(page.getByRole('alert', { name: 'خطای تقویم' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'ماهانه' })).toBeVisible();
});

test('calendar filters have names and desktop list supports keyboard activation', async ({
  page
}) => {
  await page.goto(`/dashboard/calendar?site=${site}`);
  await expect(page.getByRole('tab', { name: 'ماهانه' })).toBeVisible();
  for (const name of ['فیلتر دستهٔ محتوا', 'فیلتر وضعیت محتوا', 'فیلتر اولویت محتوا'])
    await expect(page.getByRole('combobox', { name })).toBeVisible();
  await page.getByRole('tab', { name: 'فهرست', exact: true }).click();
  const article = page.getByRole('table').getByRole('button').first();
  if (!external || (await article.count())) {
    await article.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations
  ).toEqual([]);
});

test('a late calendar response cannot replace the newly selected site', async ({ page }) => {
  test.skip(external, 'Requires the second synthetic site; production is never modified.');
  let finishOld: () => void = () => {};
  const oldResponse = new Promise<void>((resolve) => {
    finishOld = resolve;
  });
  await page.route('**/content-plans/calendar?**', async (route) => {
    const old = route.request().url().includes('/qa-site/');
    if (old) await oldResponse;
    await route.fulfill({
      json: {
        days: {},
        unscheduled: [
          { id: old ? 21 : 22, title: old ? 'پاسخ قدیمی' : 'برنامهٔ سایت دوم', status: 'planned' }
        ],
        counts: { by_status: {} },
        categories: []
      }
    });
  });
  const firstRequest = page.waitForRequest((request) =>
    request.url().includes('/qa-site/content-plans/calendar?')
  );
  await page.goto('/dashboard/calendar?site=qa-site');
  await firstRequest;
  await page.getByRole('combobox', { name: 'سایت تقویم' }).selectOption('qa-other');
  await expect(page.getByRole('button', { name: 'برنامهٔ سایت دوم' })).toBeVisible();
  finishOld();
  await page.waitForTimeout(500);
  await expect(page.getByRole('button', { name: 'پاسخ قدیمی' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'برنامهٔ سایت دوم' })).toBeVisible();
});

test('settings offers working product paths before technical details', async ({ page }) => {
  await page.goto('/dashboard/settings');
  await expect(page.getByRole('link', { name: /اتصال حساب‌ها و سایت/ })).toBeVisible();
  await expect(page.getByText('http://backend:8000')).toHaveCount(0);
  await expect(page.getByText('نسخهٔ سرویس', { exact: true })).toBeHidden();
});

test('article form preserves input after a failed save and confirms discarding changes', async ({
  page
}) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto(`/dashboard/calendar?site=${site}`);
  await page.getByRole('button', { name: '+ مقالهٔ جدید', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('عنوان مقاله', { exact: true }).fill('پیش‌نویس آزمایش؛ منتشر نشود');
  await dialog.getByLabel('کلمهٔ کلیدی اصلی', { exact: true }).fill('انتخاب پیراهن مردانه');
  expect(
    (
      await new AxeBuilder({ page })
        .include('[role="dialog"]')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations
  ).toEqual([]);
  await page.route('**/content-plans', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 503, json: { error: { message: 'ذخیرهٔ آزمایشی ناموفق' } } })
      : route.continue()
  );
  await dialog.getByRole('button', { name: 'ذخیره', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'ذخیره', exact: true })).toBeEnabled();
  await expect(dialog.getByLabel('عنوان مقاله', { exact: true })).toHaveValue(
    'پیش‌نویس آزمایش؛ منتشر نشود'
  );
  page.once('dialog', (d) => d.dismiss());
  await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible();
  page.once('dialog', (d) => d.accept());
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
});

for (const width of [375, 768, 1440]) {
  test(`add-site dialog is centered and complete at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/dashboard/overview');
    if (width < 1024)
      await page.getByRole('button', { name: 'باز و بسته کردن منو (Ctrl+B)', exact: true }).click();
    await page.getByRole('button', { name: 'افزودن سایت', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'افزودن سایت', exact: true });
    await expect(dialog).toBeVisible();
    for (const label of [
      'نام سایت',
      'دامنه',
      'شناسه (slug)',
      'حوزه کسب‌وکار',
      'زبان محتوا',
      'مکان / کشور هدف'
    ])
      await expect(dialog.getByLabel(label, { exact: true })).toBeVisible();
    await expect(dialog.getByLabel('نام سایت', { exact: true })).toBeFocused();
    if (width >= 768) {
      for (const [right, left] of [
        ['نام سایت', 'دامنه'],
        ['شناسه (slug)', 'حوزه کسب‌وکار'],
        ['زبان محتوا', 'مکان / کشور هدف']
      ]) {
        const a = await dialog.getByLabel(right, { exact: true }).boundingBox();
        const b = await dialog.getByLabel(left, { exact: true }).boundingBox();
        expect(Math.abs(a!.y - b!.y)).toBeLessThan(1);
        expect(Math.abs(a!.width - b!.width)).toBeLessThan(1);
      }
    }

    const box = await dialog.boundingBox();
    expect(Math.abs(box!.x + box!.width / 2 - width / 2)).toBeLessThan(2);
    expect(Math.abs(box!.y + box!.height / 2 - 450)).toBeLessThan(2);
    expect(box!.y).toBeGreaterThanOrEqual(10);
    expect(box!.y + box!.height).toBeLessThanOrEqual(890);
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    expect(
      (
        await new AxeBuilder({ page })
          .include('[data-add-site-dialog]')
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
          .analyze()
      ).violations
    ).toEqual([]);
    await dialog.getByLabel('نام سایت', { exact: true }).press('Escape');
    await expect(dialog).toHaveCount(0);
  });
}

test('add-site form retains failed input, creates once and continues inside the same dialog', async ({
  page
}) => {
  test.skip(external, 'Mutation responses are synthetic; never creates production sites.');
  let fail = true;
  const creates: Record<string, unknown>[] = [];
  const edits: Record<string, unknown>[] = [];
  await page.route('**/api/backend/sites', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    const body = route.request().postDataJSON();
    creates.push(body);
    if (fail)
      return route.fulfill({
        status: 503,
        json: { error: { code: 'qa_unavailable', message: 'ثبت آزمایشی ناموفق بود' } }
      });
    return route.fulfill({
      status: 201,
      json: {
        ...body,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_path: null
      }
    });
  });
  await page.route('**/api/backend/sites/qa-created', async (route) => {
    if (route.request().method() !== 'PATCH') return route.continue();
    const body = route.request().postDataJSON();
    edits.push(body);
    return route.fulfill({
      json: {
        ...creates.at(-1),
        ...body,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        workspace_path: null
      }
    });
  });
  await page.goto('/dashboard/overview');
  await page.getByRole('button', { name: 'افزودن سایت', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'افزودن سایت', exact: true });
  await dialog.getByLabel('نام سایت', { exact: true }).fill('سایت آزمایش رابط');
  await dialog
    .getByLabel('دامنه', { exact: true })
    .fill('https://shop.example.test/path?discard=this');
  await dialog.getByLabel('شناسه (slug)', { exact: true }).fill('qa-created');
  await dialog.getByLabel('حوزه کسب‌وکار', { exact: true }).selectOption('ecommerce');
  await dialog.getByLabel('زبان محتوا', { exact: true }).selectOption('en-US');
  await dialog.getByLabel('مکان / کشور هدف', { exact: true }).selectOption('GB');
  await dialog.getByRole('button', { name: 'ایجاد سایت و ادامه', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('ثبت آزمایشی ناموفق بود');
  await expect(dialog.getByLabel('نام سایت', { exact: true })).toHaveValue('سایت آزمایش رابط');
  fail = false;
  await dialog.getByRole('button', { name: 'ایجاد سایت و ادامه', exact: true }).click();
  await expect(dialog.getByText('مرحله ۲ — اتصال‌ها و تست مجوز', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/dashboard\/overview$/);
  expect(creates).toHaveLength(2);
  expect(creates[1]).toMatchObject({
    site_id: 'qa-created',
    name: 'سایت آزمایش رابط',
    canonical_url: 'https://shop.example.test/',
    wp_url: 'https://shop.example.test',
    business_type: 'ecommerce',
    language: 'en-US',
    country: 'GB',
    timezone: 'Europe/London'
  });
  await dialog.getByRole('button', { name: 'بازگشت', exact: true }).click();
  await expect(dialog.getByLabel('دامنه', { exact: true })).toBeDisabled();
  await dialog.getByLabel('نام سایت', { exact: true }).fill('نام ویرایش‌شده');
  await dialog.getByRole('button', { name: 'ذخیره اطلاعات و ادامه', exact: true }).click();
  await expect(dialog.getByText('مرحله ۲ — اتصال‌ها و تست مجوز', { exact: true })).toBeVisible();
  expect(edits).toHaveLength(1);
  expect(edits[0]).toMatchObject({
    name: 'نام ویرایش‌شده',
    business_type: 'ecommerce',
    language: 'en-US',
    country: 'GB'
  });
  expect(creates).toHaveLength(2);
});
