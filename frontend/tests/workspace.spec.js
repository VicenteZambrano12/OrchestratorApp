import { expect, test } from '@playwright/test'
import { mockWorkspace, plan, sendPrompt } from './workspace-fixtures.js'

async function expectAdaptive(page) {
  const result = await page.evaluate(() => {
    const candidates = [...document.querySelectorAll('button, input, select, textarea, summary, a[href]')]
    const undersized = candidates.filter((element) => {
      const box = element.getBoundingClientRect()
      const style = getComputedStyle(element)
      return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && !element.closest('[inert]') &&
        (box.width < 43.9 || box.height < 43.9)
    }).map((element) => ({
      name: element.getAttribute('aria-label') || element.textContent,
      width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height,
    }))
    const overflow = [...document.querySelectorAll('.exercise-table-scroll, .routine-maker-table-scroll, .routines-report, .explainer-card, .topbar, dialog[open]')]
      .filter((element) => element.clientWidth && element.scrollWidth > element.clientWidth + 1)
      .map((element) => element.className)
    const outside = [...document.querySelectorAll('.app-shell *')].filter((element) => {
      const box = element.getBoundingClientRect()
      return box.width > 0 && box.right + scrollX > innerWidth + 1
    }).slice(0, 10).map((element) => ({
      tag: element.tagName, className: element.className, right: element.getBoundingClientRect().right + scrollX,
    }))
    return { width: document.documentElement.scrollWidth, viewport: innerWidth, undersized, overflow, outside }
  })
  expect(result.width, JSON.stringify(result.outside)).toBeLessThanOrEqual(result.viewport)
  expect(result.undersized).toEqual([])
  expect(result.overflow).toEqual([])
}

for (const width of [375, 768, 1024, 1440]) {
  test(`workspace, routine editing and mobile sheets adapt at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const writes = await mockWorkspace(page)
    await page.goto('/')
    await expect(page.locator('.app-shell')).toBeVisible()
    await expect(page.locator('html')).toHaveClass('dark')
    await expect(page.locator('.training-panel')).toBeVisible()
    await expectAdaptive(page)

    const guidance = page.locator('.topbar').getByRole('button', { name: 'A little guidance' })
    await guidance.click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Close guidance' })).toBeFocused()
    await expectAdaptive(page)
    if (width < 768) {
      const position = await page.getByRole('dialog').boundingBox()
      expect(position.y + position.height).toBeCloseTo(1000, 0)
    }
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(guidance).toBeFocused()

    const profile = page.locator('.topbar').getByRole('button', { name: /Change user/ })
    await profile.click()
    await expect(page.getByRole('dialog', { name: 'Choose your user' })).toBeVisible()
    await expectAdaptive(page)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(profile).toBeFocused()

    await page.getByRole('button', { name: 'My Routine', exact: true }).click()
    await expect(page.getByRole('heading', { name: plan.name + '.' })).toBeVisible()
    await expectAdaptive(page)
    await page.getByRole('button', { name: 'Edit workout', exact: true }).click()
    await expectAdaptive(page)
    const add = page.getByRole('button', { name: 'Add exercise to Push' })
    await add.click()
    await expect(page.getByRole('dialog', { name: 'Add exercise', exact: true })).toBeVisible()
    await expectAdaptive(page)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(add).toBeFocused()

    await page.getByRole('button', { name: 'Done editing', exact: true }).click()
    await expect(page.getByRole('dialog', { name: 'Update your routine?' })).toBeVisible()
    await expectAdaptive(page)
    await page.getByRole('button', { name: 'Yes, update routine' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(writes).toHaveLength(1)
    expect(writes[0].days[0].exercises[0].exercise_id).toBe(1)
    await expectAdaptive(page)
  })

  test(`structured responses and reports adapt at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await mockWorkspace(page)
    await page.goto('/')
    await expect(page.locator('.app-shell')).toBeVisible()
    await sendPrompt(page, 'Create a routine')
    await expect(page.locator('.routine-maker')).toBeVisible()
    await expectAdaptive(page)
    await sendPrompt(page, 'Explain an exercise')
    await expect(page.locator('.explainer-card')).toBeVisible()
    await page.getByRole('button', { name: 'Execution (2)' }).click()
    await expect(page.locator('.explainer-steps li')).toHaveCount(2)
    await expectAdaptive(page)
    await page.getByRole('button', { name: 'Next exercise' }).click()
    await expect(page.locator('.explainer-count')).toHaveText('2 / 2')
    for (const query of ['Last workout report', 'Compare report', 'Weekly progress report']) {
      await sendPrompt(page, query)
      await expect(page.locator('.routines-report')).toHaveCount(
        query.startsWith('Last') ? 1 : query.startsWith('Compare') ? 2 : 3,
      )
      await expectAdaptive(page)
    }
  })
}

test('workout capture and confirmation preserve inputs after a failed save', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  const writes = await mockWorkspace(page, { failWorkout: true })
  await page.goto('/')
  await page.getByRole('button', { name: 'My Routine', exact: true }).click()
  await page.getByRole('button', { name: 'Start Workout', exact: true }).click()
  await page.getByRole('spinbutton', { name: 'Bench Press set 1 reps', exact: true }).fill('8')
  await page.getByRole('spinbutton', { name: 'Bench Press set 1 weight', exact: true }).fill('40')
  await page.getByRole('checkbox', { name: 'Mark Bench Press complete', exact: true }).click()
  await expectAdaptive(page)
  await page.getByRole('button', { name: 'Finish workout', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Finish and save your workout?' })).toBeVisible()
  await expectAdaptive(page)
  await page.getByRole('button', { name: 'Yes, finish and save' }).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Could not save workout')
  expect(writes).toHaveLength(1)
  await page.getByRole('button', { name: 'Keep working out' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('spinbutton', { name: 'Bench Press set 1 reps', exact: true })).toHaveValue('8')
  await expect(page.getByRole('button', { name: 'Finish workout', exact: true })).toBeFocused()
})

test('long data, 200% text, Spanish and saved light mode stay usable', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await page.addInitScript(() => { localStorage.setItem('form-theme', 'light') })
  await mockWorkspace(page)
  await page.goto('/')
  await expect(page.locator('.app-shell')).toBeVisible()
  await expect(page.locator('html')).not.toHaveClass('dark')
  await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
  await expectAdaptive(page)
  await page.getByRole('button', { name: 'My Routine', exact: true }).click()
  await expect(page.locator('.routine-view')).toBeVisible()
  await page.locator('.routine-view h1').evaluate((element) => { element.textContent = 'LongPlanName'.repeat(20) })
  await expectAdaptive(page)
  await page.getByRole('button', { name: 'Español' }).click()
  await expect(page.getByRole('button', { name: 'Editar entrenamiento' })).toBeVisible()
  await expectAdaptive(page)
})

test('live system map preserves the complete connected agent and database tree at every width', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/')
  const popupPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: 'Open live system map in a new window' }).click()
  const popup = await popupPromise
  for (const width of [375, 768, 1024, 1440]) {
    await popup.setViewportSize({ width, height: 900 })
    await expect(popup.locator('.workflow-canvas')).toBeVisible()
    await expect(popup.locator('.workflow-node')).toHaveCount(23)
    await expect(popup.locator('.workflow-edge')).toHaveCount(24)
    await expect(popup.locator('.database-node[data-node-id="database"]')).toHaveCount(1)
    await expect(popup.locator('[data-edge-to="database"]')).toHaveCount(3)
    for (const id of ['routine_sql', 'exercise_sql', 'history_sql']) {
      await expect(popup.locator(`[data-edge-from="${id}"][data-edge-to="database"]`)).toHaveCount(1)
    }
    await expect(popup.locator('[data-node-id$="_sql"]')).toHaveCount(3)
    await expect(popup.locator('.workflow-node-list')).toHaveCount(0)
    await expect.poll(() => popup.locator('.workflow-viewport').evaluate((viewport) => {
      const bounds = viewport.getBoundingClientRect()
      return [...viewport.querySelectorAll('.workflow-node')].every((node) => {
        const box = node.getBoundingClientRect()
        return box.width > 0 && box.height > 0 && box.left >= bounds.left &&
          box.top >= bounds.top && box.right <= bounds.right && box.bottom <= bounds.bottom
      })
    })).toBe(true)
    expect(await popup.locator('.database-node').evaluate((database) => {
      const corner = database.getBoundingClientRect()
      return [...document.querySelectorAll('.workflow-node')].every((node) => {
        const box = node.getBoundingClientRect()
        return corner.left <= box.left && corner.top <= box.top
      })
    })).toBe(true)
    expect(await popup.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await popup.locator('[data-node-id="routine_maker"]').click()
    await expect(popup.locator('[data-node-id="routine_maker"]')).toHaveAttribute('aria-pressed', 'true')
    await expect(popup.getByRole('button', { name: 'Close node details' })).toBeVisible()
    await popup.locator('[data-node-id="database"]').click()
    await expect(popup.locator('.workflow-inspector h3')).toHaveText('Database')
  }
  await popup.close()
})

test('modal motion exits cleanly while keeping background focus trapped', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.setViewportSize({ width: 375, height: 800 })
  await mockWorkspace(page)
  await page.goto('/')
  const trigger = page.locator('.topbar').getByRole('button', { name: 'A little guidance' })
  await trigger.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toHaveCSS('transform', 'none')
  await expect(page.getByRole('button', { name: 'Close guidance' })).toBeFocused()
  await trigger.evaluate((element) => element.focus())
  await expect(page.getByRole('button', { name: 'Close guidance' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.locator('dialog[inert]')).toHaveCount(1)
  await expect(page.locator('dialog')).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('short viewports and empty routines keep content and sheets reachable', async ({ page }) => {
  await mockWorkspace(page, { emptyRoutine: true })
  for (const viewport of [{ width: 812, height: 375 }, { width: 1440, height: 400 }]) {
    await page.setViewportSize(viewport)
    await page.goto('/')
    await expect(page.locator('.app-shell')).toBeVisible()
    await expectAdaptive(page)
    await page.locator('.topbar').getByRole('button', { name: 'A little guidance' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByRole('button', { name: 'Got it' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.getByRole('button', { name: 'My Routine', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'No saved routine yet' })).toBeVisible()
    await expectAdaptive(page)
  }
})

test('specialist cards and long report metrics reflow at 200% text', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await mockWorkspace(page)
  await page.goto('/')
  await expect(page.locator('.app-shell')).toBeVisible()
  await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
  for (const query of ['Create a routine', 'Explain an exercise', 'Last workout report', 'Compare report', 'Weekly progress report']) {
    await sendPrompt(page, query)
    await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeDisabled()
    await expect(page.getByRole('textbox', { name: 'Message your AI coach' })).toBeEnabled()
    await expectAdaptive(page)
  }
})

test.describe('touch devices', () => {
  test.use({ isMobile: true, hasTouch: true })

  test('routine reordering and sheet dismissal work without dragging or hovering', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await mockWorkspace(page)
    await page.goto('/')
    await page.getByRole('button', { name: 'My Routine', exact: true }).tap()
    await page.getByRole('button', { name: 'Edit workout', exact: true }).tap()
    await page.getByRole('button', { name: 'Move Bench Press down', exact: true }).tap()
    await expect(page.locator('.exercise-name strong').first()).toHaveText('Overhead Press')
    await expectAdaptive(page)
    const add = page.getByRole('button', { name: 'Add exercise to Push' })
    await add.tap()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expectAdaptive(page)
    await page.getByRole('button', { name: 'Cancel', exact: true }).tap()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(add).toBeFocused()
  })
})
