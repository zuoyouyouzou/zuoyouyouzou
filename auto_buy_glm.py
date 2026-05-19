"""
GLM Coding Lite 连续包月自动抢购脚本
每日 10:00 (UTC+8) 自动尝试购买

使用方法:
  1. pip install playwright && playwright install chromium
  2. 首次运行，手动登录: python auto_buy_glm.py --login
  3. 定时抢购: python auto_buy_glm.py
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ============ 日志 ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("auto_buy.log", encoding="utf-8")],
)
log = logging.getLogger("auto_buy")

# ============ 配置 ============
TARGET_URL = "https://www.bigmodel.cn/glm-coding"
USER_DATA_DIR = Path(__file__).parent / "browser_data"
UTC8 = timezone(timedelta(hours=8))

# 页面选择器 - 首次使用需根据实际页面调整
SELECTORS = {
    "login_btn": 'button:has-text("登录")',
    "phone_login_tab": 'text=手机号登录',
    "phone_input": 'input[placeholder*="手机号"]',
    "code_btn": 'text=获取验证码',
    "code_input": 'input[placeholder*="验证码"]',
    "logged_in_indicator": ".user-info, .avatar, [class*=user]",
    "page_ready": ".plan-card, .package-item, [class*=plan]",
    "lite_tab": 'text=Lite',
    "monthly_radio": 'text=连续包月',
    "buy_btn": 'button:has-text("立即购买"), button:has-text("立即订阅"), button:has-text("购买")',
    "sold_out_badge": 'text=已售罄, text=今日已售罄, text=暂不可购',
    "confirm_btn": 'button:has-text("确认"), button:has-text("确认购买"), button:has-text("提交")',
    "agree_checkbox": 'input[type="checkbox"], .agree-check, [class*=agree]',
    "balance_radio": 'text=余额',
    "pay_btn": 'button:has-text("支付"), button:has-text("确认支付")',
    "success_msg": 'text=购买成功, text=订阅成功, text=支付成功',
}

REFRESH_INTERVAL = 0.3
POST_CLICK_TIMEOUT = 30


def beijing_now() -> datetime:
    return datetime.now(UTC8)


def ts() -> str:
    now = datetime.now(UTC8)
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"


def wait_until(h: int, m: int, s: int):
    """自旋等到北京时间 h:m:s，提前 5 秒唤醒做最后准备"""
    now = beijing_now()
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if target <= now:
        target = target.replace(day=now.day + 1)
    diff = (target - now).total_seconds()
    log.info("距离 %02d:%02d:%02d 还有 %.0f 秒，进入等待", h, m, s, diff)
    if diff > 10:
        time.sleep(diff - 8)
    while True:
        remaining = (target - datetime.now(UTC8)).total_seconds()
        if remaining <= 0:
            return
        if remaining > 0.5:
            time.sleep(remaining - 0.3)


# ============ 浏览器 ============

async def init_browser(playwright, headless: bool = False):
    """启动持久化浏览器，登录状态自动保存到 USER_DATA_DIR"""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        channel=None,
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
        ],
    )

    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh']});
        window.chrome = { runtime: {} };
    """)

    page = await context.new_page()
    return context, page


async def check_logged_in(page) -> bool:
    try:
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        # 正向检测：已登录标识
        for sel in SELECTORS["logged_in_indicator"].split(", "):
            try:
                el = page.locator(sel.strip()).first
                if await el.count() > 0 and await el.is_visible():
                    log.info("检测到登录标识: %s", sel.strip())
                    return True
            except Exception:
                continue
        # 反向检测：登录按钮存在则未登录
        login_btn = page.locator(SELECTORS["login_btn"]).first
        if await login_btn.count() > 0 and await login_btn.is_visible():
            log.info("检测到登录按钮，判定未登录")
            return False
        # 都没找到，保守判断为已登录
        log.info("未检测到明确登录/未登录标识，默认视为已登录")
        return True
    except Exception:
        return False


async def login_flow(page):
    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    log.info("请在浏览器中完成登录 (手机号/微信扫码)")
    log.info("登录成功后按 Enter 继续...")
    input(">>> 登录完成后按 Enter: ")
    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    log.info("登录状态已保存到 %s 目录", USER_DATA_DIR)


async def find_buy_button(page):
    candidates = [
        'button:has-text("立即购买")',
        'button:has-text("立即订阅")',
        'button:has-text("购买")',
        'button:has-text("订阅")',
        'a:has-text("立即购买")',
        'a:has-text("订阅")',
        '[class*=buy]',
        '[class*=purchase]',
    ]
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=200):
                text = await el.inner_text()
                log.info("找到按钮: %s → %s", sel, text.strip())
                return el
        except Exception:
            continue
    return None


async def wait_for_available(page) -> bool:
    start = time.time()
    last_state = None
    while time.time() - start < 20:
        try:
            await page.reload(wait_until="domcontentloaded")

            sold_out = False
            for sel_text in SELECTORS["sold_out_badge"].split(", "):
                try:
                    if await page.locator(sel_text.strip()).first.is_visible(timeout=300):
                        sold_out = True
                        break
                except Exception:
                    pass

            current_state = "sold_out" if sold_out else "available"
            if current_state != last_state:
                log.info("[%s] 状态: %s → %s", ts(), last_state, current_state)
                last_state = current_state

            if current_state == "available":
                btn = await find_buy_button(page)
                if btn:
                    log.info("[%s] 按钮可用!", ts())
                    return True
            await asyncio.sleep(REFRESH_INTERVAL)
        except Exception as e:
            log.debug("刷新出错: %s", e)
            await asyncio.sleep(0.5)

    log.error("本轮等待超时(20s)，未检测到可购买状态")
    return False


async def execute_purchase(page) -> bool:
    try:
        # 1. 确保 Lite + 连续包月选中
        for sel_name in ["lite_tab", "monthly_radio"]:
            try:
                el = page.locator(SELECTORS[sel_name]).first
                if await el.is_visible(timeout=200):
                    await el.click()
                    await page.wait_for_timeout(150)
                    log.info("已选择: %s", sel_name)
            except Exception:
                pass

        # 2. 点击购买
        btn = await find_buy_button(page)
        if not btn:
            log.error("找不到购买按钮")
            return False
        log.info("[%s] 点击购买!", ts())
        await btn.click()
        await page.wait_for_timeout(500)

        # 3. 同意协议
        try:
            cb = page.locator(SELECTORS["agree_checkbox"]).first
            if await cb.is_visible(timeout=2000) and not await cb.is_checked():
                await cb.click()
                log.info("已勾选协议")
        except Exception:
            pass

        # 4. 确认
        try:
            confirm = page.locator(SELECTORS["confirm_btn"]).first
            await confirm.wait_for(state="visible", timeout=5000)
            await confirm.click()
            log.info("[%s] 已点击确认", ts())
            await page.wait_for_timeout(1000)
        except PWTimeout:
            log.warning("确认按钮未出现，继续尝试支付")

        # 5. 选择余额支付
        try:
            bal = page.locator(SELECTORS["balance_radio"]).first
            if await bal.is_visible(timeout=2000):
                await bal.click()
                log.info("已选择余额支付")
        except Exception:
            pass

        # 6. 支付
        try:
            pay = page.locator(SELECTORS["pay_btn"]).first
            await pay.wait_for(state="visible", timeout=10000)
            await pay.click()
            log.info("[%s] 已点击支付", ts())
        except PWTimeout:
            log.warning("支付按钮未出现")

        # 7. 检查结果
        await page.wait_for_timeout(1500)
        try:
            success = page.locator(SELECTORS["success_msg"]).first
            await success.wait_for(state="visible", timeout=POST_CLICK_TIMEOUT * 1000)
            log.info("购买成功!")
            return True
        except PWTimeout:
            await page.screenshot(path="result_screenshot.png")
            log.warning("未能确认结果，请检查 result_screenshot.png")
            return False

    except Exception as e:
        log.exception("购买流程异常: %s", e)
        await page.screenshot(path="error_screenshot.png")
        return False


# ============ 主流程 ============

async def run_once(headless: bool = False):
    log.info("=" * 50)
    log.info("GLM Coding 自动抢购 - %s", beijing_now().isoformat())

    async with async_playwright() as p:
        context, page = await init_browser(p, headless=headless)
        try:
            logged_in = await check_logged_in(page)
            if not logged_in:
                log.error("未登录! 请先运行 python auto_buy_glm.py --login")
                return False
            log.info("登录状态: OK")

            # 提前预加载页面，到点直接刷新
            log.info("预加载页面...")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            log.info("等待目标时间 10:00:00 ...")
            wait_until(10, 0, 0)
            log.info("[%s] 到点! 开始抢购!", ts())

            for attempt in range(4):
                if attempt > 0:
                    log.info("第 %d 次重试...", attempt)
                if not await wait_for_available(page):
                    log.warning("本轮未检测到可购买状态")
                    continue
                success = await execute_purchase(page)
                if success:
                    log.info("抢购成功!")
                    return True
                log.warning("购买流程未完成")

            log.error("全部 %d 次尝试均失败", 4)
            return False
        finally:
            if not headless:
                log.info("5 秒后关闭浏览器...")
                await asyncio.sleep(5)
            await context.close()


async def login_only():
    async with async_playwright() as p:
        context, page = await init_browser(p, headless=False)
        try:
            await login_flow(page)
            log.info("登录信息已保存!")
        finally:
            await context.close()


async def dry_run():
    async with async_playwright() as p:
        context, page = await init_browser(p, headless=False)
        try:
            logged_in = await check_logged_in(page)
            log.info("登录状态: %s", "OK" if logged_in else "未登录")
            if not logged_in:
                return
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="dry_run_page.png")
            log.info("截图已保存至 dry_run_page.png")
            for name in ["lite_tab", "monthly_radio", "buy_btn", "sold_out_badge"]:
                sel = SELECTORS[name]
                try:
                    cnt = await page.locator(sel).count()
                    log.info("  %s (%s): %d 个元素", name, sel, cnt)
                except Exception as e:
                    log.info("  %s: 定位失败 - %s", name, e)
        finally:
            await context.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GLM Coding Lite 自动抢购")
    parser.add_argument("--login", action="store_true", help="仅登录并保存状态")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--dry-run", action="store_true", help="试运行，检查页面元素")
    args = parser.parse_args()

    if args.login:
        asyncio.run(login_only())
    elif args.dry_run:
        asyncio.run(dry_run())
    else:
        asyncio.run(run_once(headless=args.headless))


if __name__ == "__main__":
    main()
