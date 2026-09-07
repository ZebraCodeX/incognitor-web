import asyncio
import logging

logger = logging.getLogger(__name__)


class WebFormEngine:
    """
    Uses Playwright to fill out opt-out / data removal web forms on broker sites.

    Broker web_form_config format:
    {
      "url": "https://example.com/opt-out",
      "steps": [
        {
          "action": "goto",
          "selector": null,
          "value": "https://example.com/opt-out"
        },
        {
          "action": "fill",
          "selector": "input[name='email']",
          "value": "{email}"
        },
        {
          "action": "fill",
          "selector": "input[name='full_name']",
          "value": "{full_name}"
        },
        {
          "action": "click",
          "selector": "button[type='submit']"
        },
        {
          "action": "wait",
          "timeout_ms": 3000
        },
        {
          "action": "confirm",
          "selector": "text=confirmation"
        }
      ]
    }

    Placeholders: {full_name}, {email}, {phone}, {address}, {dob}
    """

    async def _process(self, broker, personal_data):
        from playwright.async_api import async_playwright

        if not broker.web_form_config:
            raise ValueError(f"Broker {broker.name} has no web form config")

        config = broker.web_form_config
        url = config.get("url")
        steps = config.get("steps", [])

        if not url or not steps:
            raise ValueError(f"Broker {broker.name} form config missing url or steps")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            page = await browser.new_page()

            result = {"page_title": "", "final_url": "", "evidence": ""}

            try:
                for step in steps:
                    action = step.get("action")
                    selector = step.get("selector")
                    value = step.get("value", "")

                    if action == "goto":
                        await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        result["final_url"] = page.url
                        result["page_title"] = await page.title()

                    elif action == "fill":
                        filled = self._fill_placeholders(value, personal_data)
                        await page.fill(selector, filled)

                    elif action == "type":
                        filled = self._fill_placeholders(value, personal_data)
                        await page.type(selector, filled, delay=30)

                    elif action == "click":
                        await page.click(selector, timeout=10000)

                    elif action == "wait":
                        await page.wait_for_timeout(step.get("timeout_ms", 3000))

                    elif action == "screenshot":
                        screenshot = await page.screenshot(full_page=True)
                        result["evidence"] = screenshot.hex()

                    elif action == "wait_for":
                        await page.wait_for_selector(selector, timeout=10000)

                    elif action == "extract_text":
                        element = await page.query_selector(selector)
                        if element:
                            result["page_text"] = await element.inner_text()

                    elif action == "select":
                        await page.select_option(selector, value)

                    elif action == "check":
                        await page.check(selector)

            except Exception as e:
                logger.error(f"Web form failed for {broker.name}: {e}")
                raise
            finally:
                await browser.close()

            return result

    def _fill_placeholders(self, text, personal_data):
        mapping = {
            "{full_name}": personal_data.get("full_name", ""),
            "{email}": personal_data.get("email", ""),
            "{phone}": personal_data.get("phone", ""),
            "{address}": personal_data.get("address", ""),
            "{dob}": personal_data.get("dob", ""),
        }
        for key, val in mapping.items():
            text = text.replace(key, str(val))
        return text

    def submit(self, broker, personal_data, timeout=90):
        """Synchronous wrapper for the async form filling."""
        async def _guarded():
            return await asyncio.wait_for(
                self._process(broker, personal_data), timeout=timeout
            )

        try:
            return asyncio.run(_guarded())
        except (asyncio.TimeoutError, RuntimeError):
            logger.error(f"Web form timed out or loop busy for {broker.name}")
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_guarded())
            except asyncio.TimeoutError:
                logger.error(f"Web form still timed out for {broker.name}")
                raise
            finally:
                loop.close()
