# GLM Coding 自动抢购

智谱 GLM Coding Lite 连续包月自动抢购脚本，每日 10:00 (UTC+8) 使用 Playwright 自动化浏览器抢购。

## 环境

- Python 3.x
- Windows 平台

```bash
pip install playwright && playwright install chromium
```

## 使用

```bash
# 1. 首次登录（保存浏览器状态），需手动完成登录
python auto_buy_glm.py --login

# 2. 试运行（检查页面元素是否匹配、登录是否有效）
python auto_buy_glm.py --dry-run

# 3. 手动抢购（前台浏览器，方便观察）
python auto_buy_glm.py

# 4. 无头模式（后台运行，配合定时任务使用）
python auto_buy_glm.py --headless
```

## 定时任务 (Windows 任务计划程序)

每天 09:59:55 自动执行：

1. `Win + R` → `taskschd.msc`
2. 创建基本任务 → **名称**: `GLM Auto Buy` → **触发器**: 每天 → **时间**: `09:59:55`
3. **操作**: 启动程序
   - 程序: `run_buy.bat`

4. 右键任务 → 属性:
   - **常规**: 勾选"不管用户是否登录都要运行"，勾选"使用最高权限运行"
   - **条件**: 取消"仅当计算机使用交流电源时才启动此任务"（笔记本需要）
5. 首次使用前先执行 `python auto_buy_glm.py --login` 手动登录保存状态

## 抢购流程

```
09:59:52  浏览器预热（刷新页面 + 模拟滚动/悬停，~1-3 秒）
09:59:57  高频预监控（0.5s/轮刷新，一旦按钮出现立即抢购）
10:00:00  正式抢购（4 轮重试，每轮最多 15 次点击）
```

每轮抢购流程：

```
选择 Lite + 连续包月 → 强制点击购买按钮
  ├─ 检测验证码（截图保存，退出人工处理）
  ├─ 检测"人数过多"（自动刷新重试）
  ├─ 页面跳转/弹窗出现（进入确认流程）
  └─ 确认页出现（继续支付）
      ├─ 勾选协议 → 点击确认
      ├─ 选择余额支付 → 点击支付
      └─ 检测成功提示
```

## 关键优化

| 功能 | 说明 |
|------|------|
| 资源拦截 | 抢购期间自动拦截图片/字体/CSS，reload 从 3-5s 降至亚秒级 |
| 预热时间保护 | 预热超时不阻塞流程，根据实际时间智能决定下一步 |
| 强制点击 | force click → JS click → DOM click 三级降级 |
| 验证码检测 | 点击前后双重检测，捕获即截图退出 |
| 人气过多重试 | 自动刷新重试，单轮最多 15 次 |
| Lite 专属匹配 | 优先定位 Lite 套餐卡内按钮，避免误点其他套餐 |
| 反自动化检测 | 隐藏 webdriver 标记 + 模拟人类浏览行为 |

## 故障排查

| 现象 | 解决 |
|------|------|
| 未登录错误 | 重新执行 `python auto_buy_glm.py --login` |
| 页面元素匹配不到 | 执行 `--dry-run` 查看截图 `dry_run_page.png` |
| 验证码弹出 | 查看 `captcha_screenshot.png`，手动处理 |
| 按钮找不到了 | 查看 `error_screenshot.png`，调整 SELECTORS |
| 确认结果未知 | 查看 `result_screenshot.png` |

## 文件说明

| 文件 | 说明 |
|------|------|
| `auto_buy_glm.py` | 主脚本 |
| `run_buy.bat` | Windows 批处理启动器 |
| `requirements.txt` | Python 依赖 |
| `auto_buy.log` | 运行日志 |
| `browser_data/` | 浏览器持久化数据（登录状态等） |
| `dry_run_page.png` | `--dry-run` 页面截图 |
| `error_screenshot.png` | 异常时页面截图 |
| `result_screenshot.png` | 支付后结果截图 |
