"""The agent itself: navigate -> discover -> plan -> (dry-run | fill)."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from .forms import FormMapper
from .llm import LLMClient
from .profile import Profile
from .store import ApplicationLog

CAPTCHA_HINTS = ("captcha", "recaptcha", "i'm not a robot", "verify you are human")


class JobApplyAgent:
    def __init__(self, profile: Profile, llm: LLMClient = None,
                 log: ApplicationLog = None,
                 headless: bool = None):
        self.profile = profile
        self.llm = llm or LLMClient()
        self.log = log or ApplicationLog()
        env_headless = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"
        self.headless = env_headless if headless is None else headless

    # ---- page helpers ------------------------------------------------
    @staticmethod
    def _guess_job_meta(page) -> Dict[str, str]:
        """Best-effort job title / company from the page text."""
        try:
            text = page.inner_text("body")[:4000]
        except Exception:
            return {"job_title": "", "company": ""}
        title = ""
        m = re.search(r"(?im)^(?:job title|position|role)\s*[:\-]\s*(.+)$", text)
        if m:
            title = m.group(1).strip()
        else:
            try:
                h1 = page.inner_text("h1") if page.query_selector("h1") else ""
                title = h1.strip().splitlines()[0][:80]
            except Exception:
                title = ""
        return {"job_title": title, "company": ""}

    def _detect_blockers(self, page) -> List[str]:
        blockers: List[str] = []
        try:
            text = page.inner_text("body").lower()
        except Exception:
            return blockers
        for hint in CAPTCHA_HINTS:
            if hint in text:
                blockers.append("CAPTCHA/human-verification detected")
                break
        # Login walls: password field on an application page with no apply form
        try:
            pw = page.query_selector_all("input[type='password']")
            forms = page.query_selector_all("form")
            if pw and not forms:
                blockers.append("login wall detected (password field, no form)")
        except Exception:
            pass
        return blockers

    # ---- main entry ---------------------------------------------------
    def apply(self, url: str, dry_run: bool = True,
              confirm_submit: bool = True) -> Dict[str, Any]:
        """Run the agent against one application URL.

        Returns a result dict with the fill plan, blockers, and log id.
        In dry-run mode nothing is typed into the page and nothing is
        submitted.
        """
        from playwright.sync_api import sync_playwright

        result: Dict[str, Any] = {
            "url": url, "mode": "dry-run" if dry_run else "submitted",
            "status": "planned", "blockers": [], "actions": [],
            "job_title": "", "company": "",
        }

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)

            meta = self._guess_job_meta(page)
            result.update(meta)
            blockers = self._detect_blockers(page)
            result["blockers"] = blockers

            mapper = FormMapper(self.profile, self.llm,
                                job_title=meta["job_title"],
                                company=meta["company"])
            plans = mapper.build_plan(page)
            actions = mapper.fill(page, plans, dry_run=dry_run)
            result["actions"] = actions

            if not dry_run and not blockers:
                if confirm_submit:
                    answer = input("Submit this application? [y/N] ").strip().lower()
                    if answer != "y":
                        result["status"] = "planned"
                        result["note"] = "submission cancelled by user"
                        browser.close()
                        return self._finalize(result)
                submitted = self._try_submit(page)
                result["status"] = "submitted" if submitted else "planned"
                if not submitted:
                    result["note"] = "no submit button found; form filled only"
            elif blockers:
                result["status"] = "blocked"
                result["note"] = "; ".join(blockers)

            try:
                result["screenshot"] = self._shot(page)
            except Exception:
                pass
            browser.close()

        return self._finalize(result)

    @staticmethod
    def _try_submit(page) -> bool:
        for sel in ("button[type='submit']", "input[type='submit']",
                    "button:has-text('Submit')", "button:has-text('Apply')"):
            try:
                if page.locator(sel).count():
                    page.locator(sel).first.click()
                    page.wait_for_timeout(2500)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _shot(page) -> str:
        path = os.path.join(os.getcwd(), "apply_screenshot.png")
        page.screenshot(path=path)
        return path

    def _finalize(self, result: Dict[str, Any]) -> Dict[str, Any]:
        app_id = self.log.record(
            url=result["url"], mode=result["mode"], status=result["status"],
            job_title=result.get("job_title", ""), company=result.get("company", ""),
            plan=result["actions"], note=result.get("note", ""),
        )
        result["log_id"] = app_id
        return result
