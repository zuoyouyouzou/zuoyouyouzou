# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

智谱 GLM Coding Lite 连续包月自动抢购脚本。每日 10:00 (UTC+8) 使用 Playwright 自动化浏览器抢购。

## 环境

- Python 3.x + playwright (`pip install playwright && playwright install chromium`)
- Windows 平台，运行 `run_buy.bat` 或直接 `python auto_buy_glm.py`

## 定时任务 (Windows 任务计划程序)

每天 09:59:55 自动执行抢购脚本：

1. 打开 `taskschd.msc`（任务计划程序）
2. 右侧点击 "创建基本任务"
3. **名称**: `GLM Auto Buy`
4. **触发器**: 每天，开始日期选今天
5. **时间**: `09:59:55`
6. **操作**: 启动程序
   - 程序: `run_buy.bat`
   
7. 完成创建后，右键任务 → 属性：
   - **常规**: 勾选 "不管用户是否登录都要运行"，勾选 "使用最高权限运行"
   - **条件**: 取消 "仅当计算机使用交流电源时才启动此任务"（笔记本需要）
8. 首次使用前先运行 `python auto_buy_glm.py --login` 手动登录保存状态
