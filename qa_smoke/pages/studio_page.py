from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page, expect


class StudioPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")

    def open(self) -> None:
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded")
        expect(self.page.get_by_text("MediaGen")).to_be_visible()
        expect(
            self.page.get_by_placeholder("Describe what you want to generate...")
        ).to_be_visible()

    def set_api_key(self, api_key: str) -> None:
        self.page.evaluate(
            "([key]) => localStorage.setItem('mg_api_key', key)", [api_key]
        )

    def clear_state(self) -> None:
        self.page.evaluate(
            """
            () => {
              localStorage.removeItem('mg_prompt');
              localStorage.removeItem('mg_gallery_v2');
              localStorage.removeItem('gg_active_task');
            }
            """
        )

    def select_type(self, value: str) -> None:
        self.page.get_by_role("button", name=re.compile(fr"^{value}$", re.I)).first.click()

    def select_model(self, model_label: str) -> None:
        self.page.get_by_role("button", name=re.compile(model_label, re.I)).first.click()

    def select_mode(self, mode_label: str) -> None:
        self.page.get_by_role("button", name=re.compile(mode_label, re.I)).first.click()

    def fill_prompt(self, text: str) -> None:
        self.page.get_by_placeholder("Describe what you want to generate...").fill(text)

    def upload_reference(self, image_path: Path) -> None:
        self.page.locator('input[type="file"][accept="image/*"]').first.set_input_files(
            str(image_path)
        )

    def upload_invalid_reference(self, file_path: Path) -> None:
        self.page.locator('input[type="file"][accept="image/*"]').first.set_input_files(
            str(file_path)
        )

    def click_generate(self) -> None:
        self.page.get_by_role("button", name=re.compile(r"Generate", re.I)).first.click()

    def generate_button_enabled(self) -> bool:
        return self.page.get_by_role("button", name=re.compile(r"Generate", re.I)).first.is_enabled()

    def wait_generation_started(self, timeout_ms: int) -> None:
        expect(self.page.get_by_text(re.compile("Generating|Pending", re.I))).to_be_visible(
            timeout=timeout_ms
        )

    def wait_generation_done(self, timeout_ms: int) -> None:
        expect(
            self.page.get_by_role("button", name=re.compile("Generate Again", re.I))
        ).to_be_visible(timeout=timeout_ms)

    def wait_generation_failed(self, timeout_ms: int) -> None:
        expect(self.page.get_by_text(re.compile("Generate failed|failed", re.I))).to_be_visible(
            timeout=timeout_ms
        )

    def open_gallery(self) -> None:
        self.page.get_by_role("button", name=re.compile("^Gallery$", re.I)).click()
        expect(self.page.get_by_text("Gallery")).to_be_visible()

    def result_media_url(self) -> str | None:
        if self.page.locator("video").count() > 0:
            return self.page.locator("video").first.get_attribute("src")
        if self.page.locator("img[alt]").count() > 0:
            # First visible output image on result panel.
            imgs = self.page.locator("img[alt]")
            for i in range(imgs.count()):
                src = imgs.nth(i).get_attribute("src")
                if src and src.startswith("http"):
                    return src
        return None

