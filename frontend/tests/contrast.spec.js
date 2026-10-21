import { expect, test } from '@playwright/test'
import { mockWorkspace, sendPrompt } from './workspace-fixtures.js'

async function expectTextContrast(page) {
  const failures = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const context = canvas.getContext('2d', { willReadFrequently: true })
    function rgba(color) {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = color
      context.fillRect(0, 0, 1, 1)
      const [r, g, b, alpha] = context.getImageData(0, 0, 1, 1).data
      return [r, g, b, alpha / 255]
    }
    function composite(front, back) {
      return [0, 1, 2].map((index) => front[index] * front[3] + back[index] * (1 - front[3]))
    }
    function luminance(color) {
      const channels = color.slice(0, 3).map((value) => {
        const channel = value / 255
        return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4
      })
      return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
    }
    const failures = []
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) {
      const node = walker.currentNode
      const element = node.parentElement
      if (!node.textContent.trim() || !element || element.closest('svg, script, style, option, [aria-hidden="true"], [inert], :disabled, .sr-only')) continue
      const box = element.getBoundingClientRect()
      const style = getComputedStyle(element)
      if (!box.width || !box.height || box.bottom < 0 || style.visibility === 'hidden') continue
      const ancestors = []
      let gradient = false
      for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
        const background = getComputedStyle(ancestor)
        if (background.backgroundImage !== 'none') gradient = true
        ancestors.unshift(rgba(background.backgroundColor))
      }
      // Gradient and image-backed surfaces require a visual check, not a solid-color approximation.
      if (gradient) continue
      const background = ancestors.reduce((back, front) => composite(front, back), [255, 255, 255])
      const foreground = composite(rgba(style.color), background)
      const values = [luminance(foreground), luminance(background)].sort((a, b) => a - b)
      const ratio = (values[1] + .05) / (values[0] + .05)
      if (ratio < 4.5) failures.push({
        text: node.textContent.trim().slice(0, 60), className: element.className,
        ratio: Math.round(ratio * 100) / 100, color: style.color,
      })
    }
    return failures
  })
  expect(failures).toEqual([])
}

for (const theme of ['dark', 'light']) {
  test(`${theme} workspace and specialist text meet AA contrast on solid surfaces`, async ({ page }) => {
    await page.addInitScript((theme) => { localStorage.setItem('form-theme', theme) }, theme)
    await page.setViewportSize({ width: 375, height: 1000 })
    await mockWorkspace(page)
    await page.goto('/')
    await expect(page.locator('.app-shell')).toBeVisible()
    await expectTextContrast(page)
    await sendPrompt(page, 'Create a routine')
    await expect(page.locator('.routine-maker')).toBeVisible()
    await expectTextContrast(page)
    await sendPrompt(page, 'Weekly progress report')
    await expect(page.locator('.routines-report')).toBeVisible()
    await expectTextContrast(page)
    await page.getByRole('button', { name: 'My Routine', exact: true }).click()
    await expect(page.locator('.routine-view')).toBeVisible()
    await expectTextContrast(page)
    await page.getByRole('button', { name: 'Edit workout', exact: true }).click()
    await page.getByRole('button', { name: 'Done editing', exact: true }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expectTextContrast(page)
  })
}
