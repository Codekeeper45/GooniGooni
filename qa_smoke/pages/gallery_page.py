from __future__ import annotations

import re

from playwright.sync_api import Page, expect


class GalleryPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")

    def open(self) -> None:
        self.page.goto(f"{self.base_url}/gallery", wait_until="domcontentloaded")
        expect(self.page.get_by_text("Gallery")).to_be_visible()

    def has_item_text(self, text: str) -> bool:
        return self.page.get_by_text(re.compile(re.escape(text), re.I)).count() > 0

    def card_count(self) -> int:
        return self.page.locator('button[title="Delete"]').count()

    def download_first_item(self) -> str:
        with self.page.context.expect_page() as new_page_info:
            self.page.locator('button[title="Download"]').first.click(force=True)
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded")
        return new_page.url

    def delete_first_item(self) -> None:
        self.page.locator('button[title="Delete"]').first.click(force=True)

    def wait_item_removed(self, previous_count: int, timeout_ms: int) -> None:
        expect(self.page.locator('button[title="Delete"]')).to_have_count(
            max(0, previous_count - 1), timeout=timeout_ms
        )

