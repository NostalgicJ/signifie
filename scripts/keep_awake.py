"""
Streamlit Community Cloud 앱이 잠들지 않도록 실제 브라우저로 방문합니다.
잠든 상태면 "깨우기" 버튼을 눌러 다시 띄웁니다. (GitHub Actions에서 주기 실행)

실행: python scripts/keep_awake.py [URL]
"""

import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

APP_URL = sys.argv[1] if len(sys.argv) > 1 else "https://signifie.streamlit.app/"
WAKE_BUTTON_TEXT = "get this app back up"
APP_READY_TEXT = "시니피에"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(8_000)

        wake_button = page.get_by_role("button", name=WAKE_BUTTON_TEXT)
        if wake_button.count() > 0:
            print("앱이 잠들어 있어 깨우는 중...")
            wake_button.first.click()
            page.wait_for_timeout(5_000)

        # 앱 본문은 iframe 안에서 렌더링됨
        try:
            frame = page.frame_locator("iframe").first
            frame.get_by_text(APP_READY_TEXT).first.wait_for(timeout=180_000)
            print(f"✅ 앱 정상 동작 확인: {APP_URL}")
            return 0
        except PlaywrightTimeout:
            print("❌ 앱 화면을 확인하지 못했습니다")
            page.screenshot(path="keep_awake_failure.png", full_page=True)
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
