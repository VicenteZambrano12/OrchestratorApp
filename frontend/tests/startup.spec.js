import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }))
})

async function mockStartup(page, { backend = false, pending = false } = {}) {
  const requests = { health: 0, session: 0 }
  await page.route('**/api/health', (route) => {
    requests.health += 1
    return route.fulfill({ status: backend ? 503 : 200, json: { status: 'ok' } })
  })
  await page.route('**/api/users', (route) => {
    requests.session += 1
    if (!pending) return route.fulfill({ json: [] })
  })
  return requests
}

async function expectResponsive(page) {
  const metrics = await page.evaluate(() => {
    const main = document.querySelector('.startup-screen')
    const panel = document.querySelector('.startup-panel')
    const controls = [...main.querySelectorAll('button')].map((element) => {
      const { width, height, left, right } = element.getBoundingClientRect()
      return { width, height, left, right }
    })
    return {
      viewport: window.innerWidth,
      pageWidth: document.documentElement.scrollWidth,
      panelWidth: panel.clientWidth,
      contentWidth: panel.scrollWidth,
      controls,
    }
  })
  expect(metrics.pageWidth).toBeLessThanOrEqual(metrics.viewport)
  expect(metrics.contentWidth).toBeLessThanOrEqual(metrics.panelWidth)
  for (const target of metrics.controls) {
    expect(target.width).toBeGreaterThanOrEqual(44)
    expect(target.height).toBeGreaterThanOrEqual(44)
    expect(target.left).toBeGreaterThanOrEqual(0)
    expect(target.right).toBeLessThanOrEqual(metrics.viewport)
  }
}

for (const width of [375, 768, 1024, 1440]) {
  for (const state of ['loading', 'backend', 'session']) {
    test(`${state} adapts at ${width}px without overflow or undersized targets`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await mockStartup(page, { backend: state === 'backend', pending: state === 'loading' })
      await page.goto('/')
      const title = state === 'loading' ? 'Loading your workspace'
        : state === 'backend' ? 'Backend unavailable' : 'Session unavailable'
      await expect(page.getByRole('heading', { name: title })).toBeVisible()
      await expectResponsive(page)
      if (state === 'loading') {
        await expect(page.getByRole('status')).toContainText('Checking the server')
        await expect(page.locator('.startup-preview')).toHaveCSS('animation-name', 'none')
      } else {
        await expect(page.getByRole('alert')).not.toBeEmpty()
        await expect(page.getByRole('heading', { name: title })).toBeFocused()
      }
    })
  }
}

test('session retry does not repeat a successful backend check', async ({ page }) => {
  const requests = await mockStartup(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Session unavailable' })).toBeFocused()
  const baseline = { ...requests }
  await page.keyboard.press('Tab')
  const retry = page.getByRole('button', { name: 'Retry' })
  await expect(retry).toBeFocused()
  await expect(retry).toHaveCSS('outline-style', 'solid')
  await page.keyboard.press('Enter')
  await expect.poll(() => requests.session).toBe(baseline.session + 1)
  await expect(page.getByRole('heading', { name: 'Session unavailable' })).toBeVisible()
  expect(requests.health).toBe(baseline.health)
})

test('backend failure wins and backend retry preserves the session error', async ({ page }) => {
  const requests = await mockStartup(page, { backend: true })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Backend unavailable' })).toBeVisible()
  const baseline = { ...requests }
  await page.unroute('**/api/health')
  await page.route('**/api/health', (route) => {
    requests.health += 1
    return route.fulfill({ json: { status: 'ok' } })
  })
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('heading', { name: 'Session unavailable' })).toBeVisible()
  expect(requests.health).toBe(baseline.health + 1)
  expect(requests.session).toBe(baseline.session)
})

test('Spanish recovery reflows with 200% text', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 })
  await mockStartup(page)
  await page.unroute('**/api/users')
  await page.route('**/api/users', (route) => route.fulfill({
    json: [{ id: 1, username: 'Test user', weight_unit: 'kg' }],
  }))
  await page.route('**/api/1/key', (route) => route.fulfill({ status: 503 }))
  await page.goto('/')
  await page.getByRole('button', { name: 'Español' }).click()
  await expect(page.getByRole('heading', { name: 'Sesión no disponible' })).toBeVisible()
  await page.evaluate(() => { document.documentElement.style.fontSize = '28px' })
  await expectResponsive(page)
  await expect(page.getByRole('button', { name: 'Reintentar' })).toBeVisible()
})

test('unbroken recovery messages wrap without clipping', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 })
  await mockStartup(page)
  await page.goto('/')
  await expect(page.getByRole('alert')).toBeVisible()
  // Exercise arbitrary API error text without changing the production API contract.
  await page.getByRole('alert').evaluate((element) => { element.textContent = 'x'.repeat(500) })
  await expectResponsive(page)
  await expect(page.getByRole('alert')).toHaveCSS('overflow-wrap', 'anywhere')
})

test('normal motion settles and exiting recovery controls become inert', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 375, height: 900 })
  await mockStartup(page, { backend: true })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Backend unavailable' })).toBeVisible()
  await expect(page.locator('.startup-screen')).toHaveCSS('transform', 'none')
  await page.unroute('**/api/health')
  await page.route('**/api/health', () => {})
  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.locator('.startup-screen[inert]')).toHaveCount(1)
  await expect(page.locator('.startup-screen[inert]')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Session unavailable' })).toBeVisible()
})

test('the workspace mounts only after both prerequisites are ready', async ({ page }) => {
  let healthRoute
  let sessionReady = false
  let routineRequests = 0
  await page.route('**/api/health', (route) => { healthRoute = route })
  await page.route('**/api/users', (route) => route.fulfill({
    json: [{ id: 1, username: 'Test user', weight_unit: 'kg' }],
  }))
  await page.route('**/api/1/key', async (route) => {
    await route.fulfill({ json: {} })
    sessionReady = true
  })
  await page.route('**/api/users/1/routine', (route) => {
    routineRequests += 1
    return route.fulfill({ json: null })
  })
  await page.route('**/api/users/1/days', (route) => route.fulfill({ json: [] }))
  await page.goto('/')
  await expect.poll(() => sessionReady && Boolean(healthRoute)).toBe(true)
  await expect(page.getByRole('heading', { name: 'Loading your workspace' })).toBeVisible()
  expect(routineRequests).toBe(0)
  await healthRoute.fulfill({ json: { status: 'ok' } })
  await expect(page.locator('.app-shell:not(.skeleton-shell)')).toBeVisible()
  await expect(page.locator('.startup-screen')).toHaveCount(0)
  await expect.poll(() => routineRequests).toBeGreaterThan(0)
})

test('startup text and action colors meet WCAG AA contrast', async ({ page }) => {
  await mockStartup(page)
  await page.goto('/')
  await expect(page.getByRole('alert')).toBeVisible()
  const ratios = await page.evaluate(() => {
    function luminance(color) {
      const channels = color.match(/[\d.]+/g).slice(0, 3).map(Number).map((value) => {
        const channel = value / 255
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
      })
      return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
    }
    return [...document.querySelectorAll('.startup-screen h1, .startup-screen p, .startup-screen button')]
      .map((element) => {
        const style = getComputedStyle(element)
        const background = element.tagName === 'BUTTON' ? style.backgroundColor
          : getComputedStyle(document.querySelector('.startup-panel')).backgroundColor
        const values = [luminance(style.color), luminance(background)].sort((a, b) => a - b)
        return (values[1] + 0.05) / (values[0] + 0.05)
      })
  })
  for (const ratio of ratios) expect(ratio).toBeGreaterThanOrEqual(4.5)
})
