from __future__ import annotations

import argparse
import base64
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from playwright.sync_api import Browser, Error, sync_playwright

from pages.gallery_page import GalleryPage
from pages.studio_page import StudioPage


ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+Xf8AAAAASUVORK5CYII="
)


@dataclass
class SmokeConfig:
    base_url: str
    api_url: str
    api_key: str
    headless: bool
    timeout_ms: int
    artifacts_dir: Path
    chrome_exe: str


@dataclass
class ScenarioResult:
    name: str
    status: str
    details: str
    screenshot: str | None
    started_at: str
    finished_at: str


class SmokeRunner:
    def __init__(self, config: SmokeConfig) -> None:
        self.config = config
        self.run_dir = self._create_run_dir()
        self.assets_dir = self.run_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.reference_image = self.assets_dir / "reference.png"
        self.invalid_file = self.assets_dir / "invalid.txt"
        self._prepare_assets()
        self.results: list[ScenarioResult] = []

    def _create_run_dir(self) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        run_dir = self.config.artifacts_dir / ts
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _prepare_assets(self) -> None:
        self.reference_image.write_bytes(base64.b64decode(ONE_PIXEL_PNG_BASE64))
        self.invalid_file.write_text("this is not an image", encoding="utf-8")

    def run(self) -> None:
        scenarios: list[tuple[str, Callable[[Browser], tuple[str, str | None]]]] = [
            ("UI Load And Core Elements", self._scenario_ui_load),
            ("Model Selection And Modes", self._scenario_model_switching),
            ("Negative: Generate Without Prompt", self._scenario_negative_no_prompt),
            ("Negative: Unsupported Upload Format", self._scenario_negative_bad_upload),
            ("E2E: Flux Image Generate -> Download -> Gallery -> Delete", self._scenario_image_e2e),
            ("Video Smoke: AniSora T2V Start", self._scenario_video_anisora_smoke),
            ("Video Smoke: Phr00t WAN 2.2 Start", self._scenario_video_phr00t_smoke),
        ]

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.config.headless,
                executable_path=self.config.chrome_exe,
                args=["--disable-dev-shm-usage"],
            )
            for scenario_name, scenario_fn in scenarios:
                started_at = datetime.now(timezone.utc).isoformat()
                screenshot = None
                try:
                    details, screenshot = scenario_fn(browser)
                    self.results.append(
                        ScenarioResult(
                            name=scenario_name,
                            status="PASSED",
                            details=details,
                            screenshot=screenshot,
                            started_at=started_at,
                            finished_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )
                except SkipScenario as exc:
                    self.results.append(
                        ScenarioResult(
                            name=scenario_name,
                            status="SKIPPED",
                            details=str(exc),
                            screenshot=None,
                            started_at=started_at,
                            finished_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    failure_path = self.run_dir / f"{self._slug(scenario_name)}_failed.png"
                    self.results.append(
                        ScenarioResult(
                            name=scenario_name,
                            status="FAILED",
                            details=f"{type(exc).__name__}: {exc}",
                            screenshot=str(failure_path) if failure_path.exists() else None,
                            started_at=started_at,
                            finished_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )
            browser.close()

        self._write_report()

    def _new_studio(self, browser: Browser):
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(20000)
        studio = StudioPage(page, self.config.base_url)
        studio.open()
        if self.config.api_key:
            studio.set_api_key(self.config.api_key)
            page.reload(wait_until="domcontentloaded")
        studio.clear_state()
        page.reload(wait_until="domcontentloaded")
        return context, page, studio

    def _scenario_ui_load(self, browser: Browser) -> tuple[str, str]:
        context, page, _studio = self._new_studio(browser)
        try:
            page.get_by_text("MediaGen").first.wait_for(timeout=10000)
            page.get_by_role("button", name="Gallery").first.wait_for(timeout=10000)
            shot = self._shot("ui_load")
            page.screenshot(path=shot, full_page=True)
            return "Main page and core controls are visible.", str(shot)
        finally:
            context.close()

    def _scenario_model_switching(self, browser: Browser) -> tuple[str, str]:
        context, page, studio = self._new_studio(browser)
        try:
            studio.select_type("Video")
            studio.select_model("AniSora")
            studio.select_model("Phr00t WAN 2.2")
            studio.select_mode("Text2Video")
            studio.select_mode("Image2Video")
            studio.select_type("Image")
            studio.select_model("Flux.1 dev")
            studio.select_model("Pony V6 XL")
            studio.select_mode("Text to Image")
            studio.select_mode("Image to Image")
            shot = self._shot("model_switch")
            page.screenshot(path=shot, full_page=True)
            return "Type/model/mode switching works.", str(shot)
        finally:
            context.close()

    def _scenario_negative_no_prompt(self, browser: Browser) -> tuple[str, str]:
        context, page, studio = self._new_studio(browser)
        try:
            studio.fill_prompt("")
            if studio.generate_button_enabled():
                raise AssertionError("Generate button should be disabled without prompt.")
            shot = self._shot("negative_no_prompt")
            page.screenshot(path=shot, full_page=True)
            return "Generate button stays disabled without prompt.", str(shot)
        finally:
            context.close()

    def _scenario_negative_bad_upload(self, browser: Browser) -> tuple[str, str]:
        context, page, studio = self._new_studio(browser)
        try:
            studio.select_type("Video")
            studio.select_mode("Image2Video")
            studio.upload_invalid_reference(self.invalid_file)
            time.sleep(1.0)
            if page.locator('img[alt="Reference Image"]').count() > 0:
                raise AssertionError("Invalid upload should not appear as image reference.")
            shot = self._shot("negative_bad_upload")
            page.screenshot(path=shot, full_page=True)
            return "Unsupported file is rejected as reference.", str(shot)
        finally:
            context.close()

    def _scenario_image_e2e(self, browser: Browser) -> tuple[str, str]:
        if not self.config.api_key:
            raise SkipScenario("Missing E2E_API_KEY: full-chain generation is blocked by 403.")

        context, page, studio = self._new_studio(browser)
        try:
            prompt = f"qa smoke image {int(time.time())}"
            studio.select_type("Image")
            studio.select_model("Flux.1 dev")
            studio.select_mode("Text to Image")
            studio.fill_prompt(prompt)
            studio.click_generate()
            studio.wait_generation_started(timeout_ms=60000)
            studio.wait_generation_done(timeout_ms=self.config.timeout_ms)

            media_url = studio.result_media_url()
            if not media_url:
                raise AssertionError("Could not read result URL from UI.")

            downloaded_path = self.run_dir / "downloads" / "image_result.bin"
            downloaded_path.parent.mkdir(parents=True, exist_ok=True)
            self._download_with_auth(media_url, downloaded_path)
            if downloaded_path.stat().st_size <= 64:
                raise AssertionError("Downloaded file is unexpectedly small.")

            studio.open_gallery()
            gallery = GalleryPage(page, self.config.base_url)
            if not gallery.has_item_text("Flux"):
                raise AssertionError("Generated item was not found in gallery.")
            before = gallery.card_count()
            gallery.delete_first_item()
            gallery.wait_item_removed(previous_count=before, timeout_ms=10000)

            shot = self._shot("image_e2e")
            page.screenshot(path=shot, full_page=True)
            return "Full image chain passed: generate/view/download/gallery/delete.", str(shot)
        finally:
            context.close()

    def _scenario_video_anisora_smoke(self, browser: Browser) -> tuple[str, str]:
        return self._run_video_start_smoke(browser, "AniSora", "anisora")

    def _scenario_video_phr00t_smoke(self, browser: Browser) -> tuple[str, str]:
        return self._run_video_start_smoke(browser, "Phr00t WAN 2.2", "phr00t")

    def _run_video_start_smoke(
        self, browser: Browser, model_label: str, short_name: str
    ) -> tuple[str, str]:
        if not self.config.api_key:
            raise SkipScenario("Missing E2E_API_KEY: video smoke is blocked by 403.")

        context, page, studio = self._new_studio(browser)
        try:
            studio.select_type("Video")
            studio.select_model(model_label)
            studio.select_mode("Text2Video")
            studio.fill_prompt(f"qa smoke video {short_name} {int(time.time())}")
            studio.click_generate()
            studio.wait_generation_started(timeout_ms=60000)

            # Smoke-check: важен старт пайплайна и отсутствие немедленной ошибки в UI.
            try:
                studio.wait_generation_failed(timeout_ms=30000)
                raise AssertionError(f"{model_label}: UI reported failed on start.")
            except Error:
                pass

            shot = self._shot(f"video_{short_name}_started")
            page.screenshot(path=shot, full_page=True)
            return f"{model_label}: generation starts and queue/processing state is visible.", str(shot)
        finally:
            context.close()

    def _download_with_auth(self, url: str, target_path: Path) -> None:
        headers = {"X-API-Key": self.config.api_key} if self.config.api_key else {}
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        target_path.write_bytes(resp.content)

    def _write_report(self) -> None:
        report_path = self.run_dir / "SMOKE_REPORT.md"
        lines = [
            "# Smoke Test Report",
            "",
            f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
            f"- Base URL: `{self.config.base_url}`",
            f"- API URL: `{self.config.api_url}`",
            f"- API key provided: `{'yes' if bool(self.config.api_key) else 'no'}`",
            "",
            "## Results",
            "",
            "| Scenario | Status | Details | Screenshot |",
            "|---|---|---|---|",
        ]
        for r in self.results:
            shot = f"`{r.screenshot}`" if r.screenshot else "-"
            details = r.details.replace("|", "\\|")
            lines.append(f"| {r.name} | {r.status} | {details} | {shot} |")

        passed = sum(1 for r in self.results if r.status == "PASSED")
        failed = sum(1 for r in self.results if r.status == "FAILED")
        skipped = sum(1 for r in self.results if r.status == "SKIPPED")
        lines.extend(
            [
                "",
                "## Summary",
                "",
                f"- Passed: **{passed}**",
                f"- Failed: **{failed}**",
                f"- Skipped: **{skipped}**",
                "",
            ]
        )
        report_path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
        return "_".join(part for part in cleaned.split("_") if part)

    def _shot(self, name: str) -> Path:
        return self.run_dir / f"{self._slug(name)}.png"


class SkipScenario(Exception):
    pass


def parse_args() -> SmokeConfig:
    parser = argparse.ArgumentParser(description="Run E2E smoke tests for Gooni Gooni frontend/backend.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("E2E_BASE_URL", "http://34.73.173.191"),
        help="Frontend base URL.",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("E2E_API_URL", "https://yapparov-emir-f--gooni-api.modal.run"),
        help="Backend API URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("E2E_API_KEY", ""),
        help="API key passed as X-API-Key.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=int(os.getenv("E2E_TIMEOUT_MINUTES", "8")),
        help="Generation wait timeout in minutes.",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=os.getenv("E2E_ARTIFACTS_DIR", "qa_smoke/artifacts"),
        help="Directory for screenshots and markdown report.",
    )
    parser.add_argument(
        "--chrome-exe",
        default=os.getenv("E2E_CHROME_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        help="Path to Chrome executable.",
    )
    args = parser.parse_args()
    return SmokeConfig(
        base_url=args.base_url,
        api_url=args.api_url,
        api_key=args.api_key,
        headless=args.headless,
        timeout_ms=max(60000, args.timeout_minutes * 60 * 1000),
        artifacts_dir=Path(args.artifacts_dir).resolve(),
        chrome_exe=args.chrome_exe,
    )


def main() -> None:
    cfg = parse_args()
    runner = SmokeRunner(cfg)
    runner.run()
    print(f"Smoke run finished. Artifacts: {runner.run_dir}")


if __name__ == "__main__":
    main()
