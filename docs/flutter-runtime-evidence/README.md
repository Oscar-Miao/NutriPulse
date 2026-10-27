# Flutter 模拟器运行证据

本目录截图来自 Flutter 版本，使用独立 QA 数据库及合成资料。识餐、对话使用 `client/tool/mock_agent.py` 固定返回，不用于评价 AI 质量。

| 场景 | 截图 |
| --- | --- |
| 饮食看板与导航 | [饮食](flutter-diet.png) |
| 健身看板与计划 | [健身](flutter-fitness.png) |
| 营养预算与场景选择 | [吃什么](flutter-eat.png) |
| 真实接口生成推荐 | [推荐卡片](flutter-recommendations.png) |
| 能量复合图与周期选择 | [数据](flutter-analytics.png) |
| 档案与目标 | [个人](flutter-profile.png) |
| 人工核对识餐营养 | [复核表单](flutter-review.png) |
| 相册识餐确认后返回账本 | [确认入账](flutter-scan-confirmed.png) |
| Agent 回复与可确认方案 | [对话](flutter-chat.png) |
| 对话确认后回到饮食页 | [对话预记](flutter-chat-confirmed.png) |

识餐照片是本机测试画面的截图，Mock 返回的“QA 测试米饭”为协议测试数据。页面中照片预览内的字样属于测试图片，不是当前请求的提示信息。

自动化检查及未验收边界见 [Flutter 迁移验收](../Flutter迁移验收.md)。
