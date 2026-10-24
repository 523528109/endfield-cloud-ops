# 测试与当前状态

日期：2026-10-24 / 2026-10-25  
环境：Ubuntu 24.04、MaaEnd **v2.35.0**、MaaFramework、Google Chrome 156、headless sway

## 已验证

| 项目 | 结果 |
| --- | --- |
| 面板登录 / 初始化 / 多账号 / 会话 | 通过 |
| 实时画面（2s / 1s / 1s3 / 1s5） | 通过；4 档帧率实测符合预期 |
| 任务库 | 49 项，39 项带 MXU 可调设置 |
| MXU 设置编辑 | switch / select / checkbox / input 保存与恢复通过 |
| Maa 预设 dry-run | 全套日常 13 项、快速日常 5 项、实时辅助 1 项、基质刷取 1 项 |
| 面板启动 / 停止 | QuickDaily 5 项与定时任务 11 项均实际启动并停止；Chrome / runner / sway 无残留 |
| 启动阶段停止 | 识别为手动停止，不再误报 `[X] 启动浏览器失败` |
| Maa 更新 | v2.34.0 → v2.35.0，自检 15/15，覆盖项基线正常，失败可回滚 |
| 定时任务 | 04:00 / 16:00，写入 `maa` crontab |
| VNC 接管 | `/vnc/vnc.html` + `/vnc/websockify` 反向代理通过 |
| 移动端布局 | 390×844 通过 |
| 登录输入框对齐 / 重复 UI 清理 / Logo | 通过 |
| 桌面深色 / 浅色 | 通过 |

## 完整日常实测

2026-10-24 14:08 的 `webcloud-full` 11 项：

- 成功 8 项：`WebStartGame`（云排队约 41 分钟）、`VisitFriends`、`DijiangRewards`、`DeliveryJobs`、`SellProduct`、`AutoStockpile`、`AutoStockStaple`、`GearAssembly`
- 失败 3 项：`CreditShoppingN2`（当时角色停在 Baker 消息状态）、`WeaponUpgrade`（材料不足）、`DailyRewards`（活动条件未满足）
- 流程完整跑完并正常收尾，失败项不会中断后续任务

`CreditShoppingN2` 在单独执行 `BakerEntry` 清理会话消息后可通过。

## 已知限制

- 云游戏排队时间不可控；`WebStartGame` 上限 2 小时，超过后按失败处理。
- `CreditShoppingN2`、`WeaponUpgrade`、`DailyRewards` 等任务依赖账号进度、材料和活动状态，失败不等于面板故障。
- Maa 预设的实际完整跑分未逐一等完；本次验证覆盖 dry-run、启动、停止和运行状态，完整日常成绩见上节。
- 面板预览帧率不影响 Maa 的识别截图通道；高频预览会增加 Chrome/CDP 负载。
- 公开部署必须自行加 HTTPS / IP 限制；面板拥有启动任务和接管画面的权限。

## 安全

- 密码使用 PBKDF2-HMAC-SHA256（26 万次迭代）加盐存储。
- 所有 `/api/*` 在存在账号后都需要会话或 token。
- 运行时账号、token、Cookie、`mxu-MaaEnd.json` 不进入仓库。
