import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.skip(
  !!process.env.UI_QA_BASE_URL,
  'Synthetic navigation/support tests never write to production.'
);
test.beforeEach(async ({ page }) => {
  await page.route('**/*', (route) =>
    ['GET', 'HEAD', 'OPTIONS'].includes(route.request().method()) ? route.continue() : route.abort()
  );
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('quick access saves route choices and ordering, while collapsed rail preserves module navigation', async ({
  page
}) => {
  await page.goto('/dashboard/overview');
  await page.getByRole('button', { name: 'ویرایش دسترسی سریع', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('در همین مرورگر');
  await dialog.getByRole('checkbox', { name: 'تقویم محتوا', exact: true }).uncheck();
  await dialog.getByRole('checkbox', { name: 'داشبورد', exact: true }).check();
  await dialog.getByRole('button', { name: 'بالاتر: داشبورد', exact: true }).click();
  expect(
    (
      await new AxeBuilder({ page })
        .include('[role="dialog"]')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations
  ).toEqual([]);
  await dialog.getByRole('button', { name: 'ذخیرهٔ دسترسی سریع', exact: true }).click();
  const quick = page.getByRole('navigation', { name: 'دسترسی‌های سریع', exact: true });
  await expect(
    quick.getByRole('button', { name: 'دسترسی سریع: داشبورد', exact: true })
  ).toBeVisible();
  await expect(
    quick.getByRole('button', { name: 'دسترسی سریع: تقویم محتوا', exact: true })
  ).toHaveCount(0);
  const before = await quick.getByRole('button').allTextContents();
  const namesBefore = await quick
    .getByRole('button')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('aria-label')));
  expect(namesBefore[3]).toBe('دسترسی سریع: داشبورد');
  await page.reload();
  await expect(
    page
      .getByRole('navigation', { name: 'دسترسی‌های سریع' })
      .getByRole('button', { name: 'دسترسی سریع: داشبورد', exact: true })
  ).toBeVisible();
  expect(
    await page
      .getByRole('navigation', { name: 'دسترسی‌های سریع' })
      .getByRole('button')
      .allTextContents()
  ).toEqual(before);
  await page.getByRole('button', { name: 'جمع کردن منو', exact: true }).click();
  await expect(
    page.getByRole('navigation', { name: 'دسته‌های منو' }).getByRole('button')
  ).toHaveCount(5);
  await page
    .getByRole('navigation', { name: 'دسته‌های منو' })
    .getByRole('button', { name: 'سئو و رشد', exact: true })
    .click();
  await expect(page.getByRole('button', { name: 'جمع کردن منو', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'دسترسی‌های سریع' })).toBeVisible();
});

test('status refresh refetches real sources, rotates while pending, and recovers from failure', async ({
  page
}) => {
  let calls = 0;
  let delayed = false;
  let fail = false;
  await page.route('**/api/backend/jobs?**', async (route) => {
    calls++;
    if (delayed) await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill(
      fail ? { status: 503, json: { error: { message: 'QA status unavailable' } } } : { json: [] }
    );
  });
  await page.goto('/dashboard/overview');
  const refresh = page.getByRole('button', { name: 'تازه‌سازی وضعیت', exact: true });
  await expect(refresh).toBeVisible();
  await expect.poll(() => calls).toBeGreaterThan(0);
  const initial = calls;
  delayed = true;
  await refresh.click();
  await expect(refresh).toHaveAttribute('aria-busy', 'true');
  await expect(refresh).toBeDisabled();
  expect(
    await refresh.locator('svg').evaluate((node) => getComputedStyle(node).animationName)
  ).not.toBe('none');
  await expect(refresh).toHaveAttribute('aria-busy', 'false');
  expect(calls).toBeGreaterThan(initial);
  fail = true;
  await refresh.click();
  await expect(page.getByText('وضعیت تازه دریافت نشد؛ دوباره تلاش کنید.', { exact: true })).toBeVisible();
  fail = false;
  await refresh.click();
  await expect(page.getByText('وضعیت تازه دریافت نشد؛ دوباره تلاش کنید.', { exact: true })).toHaveCount(0);
});

test('support preserves a failed draft and supports ticket, reply, close and reopen in the same dialog', async ({
  page
}) => {
  let fail = true;
  const ticket = {
    id: 1,
    reference: 'SB-000001',
    owner: 'qa-user',
    subject: 'مشکل منوی آزمایشی',
    category: 'problem',
    site_id: 'qa-site',
    context_path: '/dashboard/overview',
    status: 'open',
    created_at: '2026-11-05T10:00:00Z',
    updated_at: '2026-11-05T10:00:00Z',
    messages: [
      {
        id: 1,
        author: 'qa-user',
        is_staff: 0,
        body: 'شرح مشکل آزمایشی منو',
        created_at: '2026-11-05T10:00:00Z'
      }
    ]
  };
  await page.route('**/api/backend/support/tickets**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'POST' && path.endsWith('/tickets')) {
      if (fail)
        return route.fulfill({
          status: 503,
          json: { error: { message: 'ثبت آزمایشی ناموفق بود' } }
        });
      expect(request.postDataJSON().message).toBe('شرح مشکل آزمایشی منو');
      return route.fulfill({ status: 201, json: ticket });
    }
    if (request.method() === 'POST') {
      ticket.messages.push({
        id: 2,
        author: 'qa-user',
        is_staff: 0,
        body: request.postDataJSON().message,
        created_at: '2026-11-05T10:01:00Z'
      });
      ticket.status = 'open';
      return route.fulfill({ status: 201, json: ticket });
    }
    if (request.method() === 'PATCH') {
      ticket.status = request.postDataJSON().status;
      return route.fulfill({ json: ticket });
    }
    return route.fulfill({
      json: path.endsWith('/tickets')
        ? { items: [], total: 0, is_staff: false, account: 'qa-user' }
        : ticket
    });
  });
  await page.goto('/dashboard/overview');
  await page.getByRole('button', { name: 'پشتیبانی', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(
    dialog.getByText('درخواستی در این وضعیت ثبت نشده است.', { exact: true })
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'ثبت درخواست', exact: true }).click();
  await dialog.getByRole('textbox', { name: 'عنوان درخواست', exact: true }).fill(ticket.subject);
  await dialog
    .getByRole('textbox', { name: 'توضیحات درخواست', exact: true })
    .fill('شرح مشکل آزمایشی منو');
  await dialog.getByRole('button', { name: 'ثبت درخواست پشتیبانی', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('ثبت آزمایشی ناموفق بود');
  await expect(dialog.getByRole('textbox', { name: 'توضیحات درخواست', exact: true })).toHaveValue(
    'شرح مشکل آزمایشی منو'
  );
  fail = false;
  await dialog.getByRole('button', { name: 'ثبت درخواست پشتیبانی', exact: true }).click();
  await expect(dialog.getByText('SB-000001', { exact: true })).toBeVisible();
  await dialog
    .getByRole('textbox', { name: 'پیام تازه', exact: true })
    .fill('توضیح تکمیلی آزمایشی');
  await dialog.getByRole('button', { name: 'ارسال پیام', exact: true }).click();
  await expect(dialog.getByRole('log')).toContainText('توضیح تکمیلی آزمایشی');
  await dialog.getByRole('button', { name: 'بستن درخواست', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'باز کردن دوباره', exact: true })).toBeVisible();
  expect(
    (
      await new AxeBuilder({ page })
        .include('[role="dialog"]')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
    ).violations
  ).toEqual([]);
  await dialog.getByRole('button', { name: 'باز کردن دوباره', exact: true }).click();
  await expect(dialog.getByRole('button', { name: 'بستن درخواست', exact: true })).toBeVisible();
});

