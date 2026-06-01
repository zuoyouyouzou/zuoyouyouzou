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
    "busy_msg": 'text=人数过多, text=请稍后, text=当前人数较多',
    "captcha_mask": '#tCaptchaMaskLayer, .tencent-captcha__mask-layer, [class*=captcha]',
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
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--disable-default-apps",
            "--mute-audio",
            "--hide-scrollbars",
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


async def dump_page_buttons(page):
    """调试：打印页面上所有可见按钮的文本和类名"""
    try:
        buttons = page.locator("button")
        count = await buttons.count()
        visible = []
        for i in range(min(count, 30)):
            try:
                btn = buttons.nth(i)
                if await btn.is_visible(timeout=100):
                    text = (await btn.inner_text()).strip()[:50]
                    cls = (await btn.get_attribute("class") or "")[:60]
                    visible.append(f"  [{i}] text={text!r} class={cls!r}")
            except Exception:
                continue
        if visible:
            log.info("页面上可见按钮 (%d/%d):\n%s", len(visible), count, "\n".join(visible))
        else:
            log.info("页面上未见可见按钮 (共 %d 个)", count)
    except Exception as e:
        log.debug("dump_page_buttons 出错: %s", e)


async def find_buy_button(page):
    """查找购买按钮，优先定位 Lite 套餐卡内的按钮"""
    # 优先：查找 Lite 套餐专属按钮
    lite_specific = [
        '[class*=card]:has-text("Lite") button:has-text("订阅")',
        '[class*=package]:has-text("Lite") button:has-text("订阅")',
        '[class*=plan]:has-text("Lite") button:has-text("订阅")',
        '[class*=card]:has-text("Lite") button:has-text("购买")',
        '[class*=package]:has-text("Lite") button:has-text("购买")',
        '[class*=plan]:has-text("Lite") button:has-text("购买")',
        # 新增：更宽泛的 Lite 卡片内按钮匹配
        '[class*=card]:has-text("Lite") button',
        '[class*=item]:has-text("Lite") button:has-text("订阅")',
        '[class*=item]:has-text("Lite") button:has-text("购买")',
        '[class*=box]:has-text("Lite") button:has-text("订阅")',
        '[class*=box]:has-text("Lite") button:has-text("购买")',
        # 新增：Coding Lite 相关
        'button:has-text("Coding")',
        '[class*=card]:has-text("Coding") button',
    ]
    for sel in lite_specific:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible(timeout=200):
                text = (await el.inner_text()).strip()[:30] if await el.count() > 0 else ""
                log.info("找到Lite专属按钮: %s → %s", sel, text)
                return el
        except Exception:
            continue

    # 回退：全局搜索
    candidates = [
        'button:has-text("立即购买")',
        'button:has-text("立即订阅")',
        'button:has-text("购买")',
        'button:has-text("订阅")',
        'button:has-text("开通")',
        'button:has-text("续费")',
        'button:has-text("抢购")',
        'a:has-text("立即购买")',
        'a:has-text("订阅")',
        'a:has-text("购买")',
        '[class*=buy]',
        '[class*=purchase]',
        '[class*=subscribe]',
        # 新增：el-button 类型
        'button.el-button--primary',
        '.el-button:has-text("订阅")',
        '.el-button:has-text("购买")',
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

    # 调试：打印页面上所有按钮
    log.warning("未找到购买按钮，打印页面调试信息...")
    await dump_page_buttons(page)
    await page.screenshot(path="debug_no_button.png")
    # 保存页面 HTML 片段（body 内的主要内容）
    try:
        html_snippet = await page.evaluate("""() => {
            const body = document.body;
            if (!body) return 'NO_BODY';
            // 只取前 3000 字符的关键结构
            return body.innerHTML.substring(0, 5000);
        }""")
        with open("debug_no_button.html", "w", encoding="utf-8") as f:
            f.write(html_snippet)
        log.info("调试 HTML 已保存至 debug_no_button.html")
    except Exception as e:
        log.debug("保存 HTML 失败: %s", e)
    log.info("调试截图已保存至 debug_no_button.png")
    return None


async def wait_for_available(page) -> bool:
    start = time.time()
    last_state = None
    no_button_count = 0  # 连续 available 但找不到按钮的次数
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
                no_button_count += 1
                # 连续5次 available 但找不到按钮 → 页面结构可能变了，提前终止
                if no_button_count >= 5:
                    log.error("[%s] 连续%d次检测到available但找不到按钮，页面结构可能已变更", ts(), no_button_count)
                    return False
            else:
                no_button_count = 0  # sold_out 状态时重置计数
            await asyncio.sleep(REFRESH_INTERVAL)
        except Exception as e:
            log.debug("刷新出错: %s", e)
            await asyncio.sleep(0.5)

    log.error("本轮等待超时(20s)，未检测到可购买状态")
    return False


async def force_click(page, btn, timeout=3):
    """强制点击按钮，先尝试 force click，失败则用 JS 直接触发 click 事件"""
    try:
        await btn.click(force=True, timeout=timeout * 1000)
    except Exception:
        try:
            await btn.evaluate("element => element.click()")
        except Exception:
            # 终极手段：page.evaluate + 选择器
            try:
                await page.evaluate("""
                    (selector) => {
                        const el = document.querySelector(selector) ||
                                   [...document.querySelectorAll('button')]
                                       .find(b => b.textContent.includes('订阅') || b.textContent.includes('购买'));
                        if (el) el.click();
                    }
                """, "button")
            except Exception as e:
                log.warning("所有点击方式均失败: %s", e)
                raise


async def check_captcha(page) -> bool:
    """检测腾讯验证码是否弹出"""
    try:
        mask = page.locator(SELECTORS["captcha_mask"]).first
        if await mask.is_visible(timeout=500):
            log.warning("[%s] 检测到验证码弹出!", ts())
            await page.screenshot(path="captcha_screenshot.png")
            return True
    except Exception:
        pass
    return False


async def browser_warmup(page):
    """模拟人类浏览行为，降低触发验证码概率；先刷新页面确保内容最新"""
    log.info("[%s] 浏览器预热...", ts())
    try:
        await page.reload(wait_until="domcontentloaded")
        await page.evaluate("window.scrollTo({top: 300, behavior: 'instant'})")
        await asyncio.sleep(0.4)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        await asyncio.sleep(0.3)
        for sel in ["lite_tab", "monthly_radio"]:
            try:
                el = page.locator(SELECTORS[sel]).first
                if await el.is_visible(timeout=300):
                    await el.hover()
                    await asyncio.sleep(0.2)
            except Exception:
                pass
        log.info("[%s] 预热完成", ts())
    except Exception as e:
        log.debug("预热出错: %s", e)


async def block_resources(page):
    """拦截图片/字体/媒体请求，加速抢购期间的页面刷新（不拦截 CSS，避免影响页面渲染）"""
    await page.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_()
        ),
    )


async def select_lite_monthly(page):
    """确保 Lite + 连续包月被选中"""
    for sel_name in ["lite_tab", "monthly_radio"]:
        try:
            el = page.locator(SELECTORS[sel_name]).first
            if await el.is_visible(timeout=200):
                await el.click()
                await page.wait_for_timeout(100)
        except Exception:
            pass


async def click_buy_with_busy_retry(page, max_retries=15) -> bool:
    """点击购买按钮，强制点击 + 人数过多重试 + 验证码检测"""
    base_url = page.url
    for i in range(max_retries):
        # 检测验证码
        if await check_captcha(page):
            log.error("[%s] 验证码阻断，需人工处理! 查看 captcha_screenshot.png", ts())
            return False

        await select_lite_monthly(page)

        btn = await find_buy_button(page)
        if not btn:
            log.error("[%s] 购买按钮消失", ts())
            return False

        log.info("[%s] 强制点击购买 (第%d次)", ts(), i + 1)
        try:
            await force_click(page, btn, timeout=3)
        except Exception:
            log.warning("[%s] 点击失败(3s超时)，刷新重试...", ts())
            await page.reload(wait_until="domcontentloaded")
            continue

        # 快速等待页面响应
        await page.wait_for_timeout(200)

        # 检测验证码 (可能在点击后弹出)
        if await check_captcha(page):
            log.error("[%s] 点击后弹出验证码，需人工处理!", ts())
            return False

        # 检测"人数过多"
        try:
            busy = page.locator(SELECTORS["busy_msg"]).first
            if await busy.is_visible(timeout=1000):
                log.info("[%s] 检测到'人数过多'，刷新重试...", ts())
                await page.reload(wait_until="domcontentloaded")
                continue
        except Exception:
            pass

        # 检测页面跳转 (URL 变化)
        current_url = page.url
        if current_url != base_url and current_url != TARGET_URL:
            log.info("[%s] 页面已跳转: %s", ts(), current_url)
            return True

        # 检测确认按钮
        try:
            confirm = page.locator(SELECTORS["confirm_btn"]).first
            await confirm.wait_for(state="visible", timeout=3000)
            log.info("[%s] 确认页面已出现!", ts())
            return True
        except PWTimeout:
            pass

        # 检测是否有新弹窗/对话框出现 (Element-UI dialog)
        try:
            dialog = page.locator(".el-dialog, .el-message-box, [role=dialog], .modal, .popup").first
            if await dialog.is_visible(timeout=500):
                log.info("[%s] 检测到弹窗/对话框出现", ts())
                await page.screenshot(path="dialog_screenshot.png")
                return True
        except Exception:
            pass

        log.info("[%s] 未进入确认页，刷新重试...", ts())
        await page.reload(wait_until="domcontentloaded")

    log.error("重试%d次仍未进入确认页面", max_retries)
    return False


async def execute_purchase(page) -> bool:
    try:
        # 1. 点击购买，处理"人数过多"重试
        if not await click_buy_with_busy_retry(page):
            return False

        # 2. 同意协议
        try:
            cb = page.locator(SELECTORS["agree_checkbox"]).first
            if await cb.is_visible(timeout=2000) and not await cb.is_checked():
                await cb.click()
                log.info("已勾选协议")
        except Exception:
            pass

        # 3. 确认
        try:
            confirm = page.locator(SELECTORS["confirm_btn"]).first
            await confirm.click()
            log.info("[%s] 已点击确认", ts())
            await page.wait_for_timeout(1000)
        except Exception:
            log.warning("确认按钮点击失败，继续尝试支付")

        # 4. 选择余额支付
        try:
            bal = page.locator(SELECTORS["balance_radio"]).first
            if await bal.is_visible(timeout=2000):
                await bal.click()
                log.info("已选择余额支付")
        except Exception:
            pass

        # 5. 支付
        try:
            pay = page.locator(SELECTORS["pay_btn"]).first
            await pay.wait_for(state="visible", timeout=10000)
            await pay.click()
            log.info("[%s] 已点击支付", ts())
        except PWTimeout:
            log.warning("支付按钮未出现")

        # 6. 检查结果
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

async def pre_monitor(page) -> bool:
    """09:59:57 起高频监控，一旦按钮出现立即抢购，持续到 10:00:00"""
    target = beijing_now().replace(hour=10, minute=0, second=0, microsecond=0)
    if beijing_now() >= target:
        return False  # 已经过了 10:00

    wait_until(9, 59, 52)
    await browser_warmup(page)
    # 预热完成后根据当前时间决定行为，而非盲目 wait_until
    now = beijing_now()
    if now >= target:
        log.info("[%s] 预热耗时过长已过10:00，进入正式抢购", ts())
        return False
    if now >= target.replace(minute=59, second=57):
        log.info("[%s] 预热完成时已过09:59:57，直接开始预监控", ts())
    else:
        wait_until(9, 59, 57)
    log.info("[%s] 开始高频预监控 (0.5s/轮)", ts())

    last_state = None
    consecutive_failures = 0
    while datetime.now(UTC8) < target:
        try:
            await page.reload(wait_until="domcontentloaded")

            sold_out = False
            for sel_text in SELECTORS["sold_out_badge"].split(", "):
                try:
                    if await page.locator(sel_text.strip()).first.is_visible(timeout=200):
                        sold_out = True
                        break
                except Exception:
                    pass

            current_state = "sold_out" if sold_out else "available"
            if current_state != last_state:
                log.info("[%s] 状态变更: %s → %s", ts(), last_state, current_state)
                last_state = current_state

            if current_state == "available":
                log.info("[%s] 提前开放! 立即抢购!", ts())
                success = await execute_purchase(page)
                if success:
                    return True
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    log.warning("[%s] 预监控阶段连续%d次抢购失败，等待正式抢购", ts(), consecutive_failures)
                    break
                log.info("[%s] 购买未完成，继续监控...", ts())
                last_state = None  # 重置状态，继续循环
            else:
                consecutive_failures = 0

            await asyncio.sleep(0.5)
        except Exception as e:
            log.debug("预监控出错: %s", e)
            await asyncio.sleep(0.5)

    log.info("[%s] 已到 10:00，进入正式抢购", ts())
    return False


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

            # 提前预加载页面
            log.info("预加载页面...")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)

            # 抢购期间屏蔽图片/字体/媒体，加速页面刷新
            await block_resources(page)

            # 09:59:57 开始高频预监控，抢跑
            if await pre_monitor(page):
                return True

            # 10:00 正式抢购，含重试
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
            # 保存最终状态便于排查
            try:
                await page.screenshot(path="final_state.png")
                log.info("最终页面截图已保存至 final_state.png")
            except Exception:
                pass
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
            log.info("--- 页面按钮列表 ---")
            await dump_page_buttons(page)
            log.info("--- 查找购买按钮 ---")
            btn = await find_buy_button(page)
            log.info("find_buy_button 结果: %s", "找到" if btn else "未找到")
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

