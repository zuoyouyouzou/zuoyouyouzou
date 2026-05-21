# GLM Coding 自动抢购

智谱 GLM Coding Lite 连续包月自动抢购脚本，每日 10:00 (UTC+8) 自动抢购。

## 环境

```bash
pip install playwright && playwright install chromium
```

## 使用

```bash
# 1. 首次登录（保存浏览器状态）
python auto_buy_glm.py --login

# 2. 试运行（检查页面元素）
python auto_buy_glm.py --dry-run

# 3. 定时抢购
python auto_buy_glm.py

# 4. 无头模式（后台运行）
python auto_buy_glm.py --headless
```

## 配置定时任务

Windows 任务计划程序，每天 09:59:55 自动执行：

1. `Win + R` → `taskschd.msc`
2. 创建基本任务 → 名称 `GLM Auto Buy` → 每天 → `09:59:55`
3. 操作：启动程序 → `D:\mini_project\run_buy.bat`，起始于 `D:\mini_project`
4. 属性 → 常规 → 勾选"不管用户是否登录都要运行"和"使用最高权限运行"

## 抢购流程

```
09:59:52  浏览器预热（模拟人类行为）
09:59:57  高频预监控（0.5s/轮刷新检测）
10:00:00  正式抢购 + 4 轮重试
  ├─ 优先匹配 Lite 专属按钮
  ├─ 强制点击（绕过页面遮挡）
  ├─ 检测人数过多 → 刷新重试
  └─ 检测验证码 → 截图退出
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `auto_buy_glm.py` | 主脚本 |
| `run_buy.bat` | Windows 批处理启动器 |
| `requirements.txt` | Python 依赖 |
| `browser_data/` | 浏览器登录状态（首次登录后生成） |
