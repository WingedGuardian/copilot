"""Playwright browser automation tool."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool


class BrowserTool(Tool):
    """Tool for browser automation via Playwright."""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self._headless = headless
        self._timeout = timeout
        self._browser = None
        self._page = None

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Automate a web browser. "
            "Actions: navigate (go to URL), screenshot (capture page), "
            "text (extract page text), links (list links), "
            "click (click element), fill (fill form field), "
            "evaluate (run JavaScript), pdf (save as PDF), close."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate", "screenshot", "text", "links",
                        "click", "fill", "evaluate", "pdf", "close",
                    ],
                    "description": "Browser action to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for 'navigate' action)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for click/fill actions",
                },
                "value": {
                    "type": "string",
                    "description": "Value to fill or JS code to evaluate",
                },
                "path": {
                    "type": "string",
                    "description": "File path for screenshot/pdf output",
                },
            },
            "required": ["action"],
        }

    async def _ensure_browser(self) -> None:
        """Lazily initialize browser and page."""
        if self._browser is not None and self._page is not None:
            return

        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        self._page.set_default_timeout(self._timeout)

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "navigate")

        if action == "close":
            return await self._close()

        try:
            await self._ensure_browser()
        except Exception as e:
            return f"Browser init failed: {e}"

        try:
            if action == "navigate":
                return await self._navigate(kwargs.get("url", ""))
            elif action == "screenshot":
                return await self._screenshot(kwargs.get("path", "/tmp/nanobot_screenshot.png"))
            elif action == "text":
                return await self._text()
            elif action == "links":
                return await self._links()
            elif action == "click":
                return await self._click(kwargs.get("selector", ""))
            elif action == "fill":
                return await self._fill(kwargs.get("selector", ""), kwargs.get("value", ""))
            elif action == "evaluate":
                return await self._evaluate(kwargs.get("value", ""))
            elif action == "pdf":
                return await self._pdf(kwargs.get("path", "/tmp/nanobot_page.pdf"))
            else:
                return f"Unknown browser action: {action}"
        except Exception as e:
            return f"Browser error: {e}"

    async def _navigate(self, url: str) -> str:
        if not url:
            return "Error: URL required"
        await self._page.goto(url, wait_until="domcontentloaded")
        title = await self._page.title()
        return f"Navigated to {url}\nTitle: {title}"

    async def _screenshot(self, path: str) -> str:
        await self._page.screenshot(path=path, full_page=True)
        return f"Screenshot saved to {path}"

    async def _text(self) -> str:
        text = await self._page.inner_text("body")
        if len(text) > 8000:
            text = text[:8000] + "\n... (truncated)"
        return text

    async def _links(self) -> str:
        links = await self._page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: e.innerText.trim().slice(0,60), href: e.href})).slice(0, 50)"
        )
        lines = [f"  {l['text']}: {l['href']}" for l in links if l.get("href")]
        return f"Links ({len(lines)}):\n" + "\n".join(lines) if lines else "No links found."

    async def _click(self, selector: str) -> str:
        if not selector:
            return "Error: selector required"
        await self._page.click(selector)
        return f"Clicked: {selector}"

    async def _fill(self, selector: str, value: str) -> str:
        if not selector:
            return "Error: selector required"
        await self._page.fill(selector, value)
        return f"Filled {selector} with value"

    async def _evaluate(self, code: str) -> str:
        if not code:
            return "Error: JavaScript code required"
        result = await self._page.evaluate(code)
        return str(result)[:5000]

    async def _pdf(self, path: str) -> str:
        await self._page.pdf(path=path)
        return f"PDF saved to {path}"

    async def _close(self) -> str:
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None
            return "Browser closed."
        return "No browser open."
