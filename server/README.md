# NutriPulse 本地服务

Python 3.11+；运行前执行 `python -m pip install -r requirements.txt`。Pillow 用于识餐图片解码与重新编码，ReportLab 用于中文 PDF 导出。运行 `python run.py` 后，健康检查为 `GET /api/v1/health`，普通业务接口统一返回 `{ "data": ..., "request_id": "..." }`；错误返回 `code/message/request_id/retryable`。

`GET /api/v1/diagnostics/logs?limit=100` 可导出当前进程最近的请求诊断（上限 500 条，需与业务接口相同的 Bearer 令牌）。每条只含时间、请求 ID、HTTP 方法、模块、状态码、耗时、错误码及异常类型；不记录 URL/查询参数、请求正文、授权头、异常原文或健康数据。日志仅驻留内存、重启清空，响应禁止缓存；个人页“连接诊断”可经系统文件选择器保存 JSON。此接口用于本地排障，不代表持久审计或性能 SLA 监控。

局域网模式启动后，电脑终端显示 `XXXX-XXXX-XXXX-XXXX` 配对码。手机调用无须 Bearer 的 `POST /api/v1/auth/pair`，请求 `{"code":"..."}`；成功返回限时 `access_token/token_type/expires_at`，手机只把令牌存入 Android Keystore 保护的存储。配对码有效 10 分钟、仅成功一次、5 次错误后锁定；令牌最多有效 24 小时，服务重启即失效。需要新码时由电脑端使用管理员密钥调用 `POST /api/v1/auth/pair-code`（请求 `{}`），不得把管理员密钥发送给手机。全量清空个人数据后当前服务的配对令牌也会失效。旧版手工管理员令牌仍可使用，但不推荐。配对请求及令牌响应在 HTTP 上仍是明文，**只能用于可信私有网络**；不可信网络须自行配置 HTTPS，不能把这套 Demo 配对视为抗窃听的生产级认证。

## 环境配置

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `NUTRIPULSE_DB` | `server/data/nutripulse.sqlite3` | SQLite 文件位置 |
| `NUTRIPULSE_HOST` | `127.0.0.1` | 监听地址；局域网只允许明确的 RFC1918/ULA 私有网卡地址，拒绝 `0.0.0.0` 和公网地址 |
| `NUTRIPULSE_PORT` | `8787` | HTTP 端口 |
| `NUTRIPULSE_API_TOKEN` | 空 | 电脑端管理员 Bearer 密钥；局域网模式必填且至少 24 字符，建议用随机生成器创建，不需复制到手机 |
| `NUTRIPULSE_AGENT_URL` | 空 | 联网 Agent 网关 HTTPS URL（也允许本机回环 HTTP） |
| `NUTRIPULSE_AGENT_TOKEN` | 空 | Agent 网关 Bearer 令牌 |
| `NUTRIPULSE_RECOMMENDATION_WEIGHTS` | 空（使用 PRD 七项默认权重） | 可选 JSON 对象；须包含 `macro/calorie/preference/stage/scenario/diversity/feedback` 七项、每项 0–1 且合计为 1；无效配置回退默认权重并记警告 |
| `NUTRIPULSE_RSS_URL` | 空 | HTTPS RSS 资讯源，后台每 6 小时尝试刷新 |
| `NUTRIPULSE_RSS_ALLOWED_HOSTS` | 空 | 逗号分隔的额外可信域名；默认只信任 RSS 域名，文章和封面跨域时需显式加入 |
| `NUTRIPULSE_REPORT_FONT` | Windows 默认使用 `C:\Windows\Fonts\simhei.ttf` | 导出中文 PDF 的可嵌入 TTF 字体；非 Windows 可手动设置 |
| `NUTRIPULSE_BACKUP_DIR` | 数据库旁的 `backups/` | 自动日/周备份及迁移前备份目录 |

联网网关请求为 `POST` JSON：`{"agent_type":"...","input":{...}}`。响应是业务 JSON 对象。当前类型：

- `food_vision`: `items` 数组，每项含 `name,estimated_grams,kcal,carb_g,protein_g,fat_g,confidence`；可含 `warnings`。
- `meal_recommendation`: `recipe_ids` 数组，只能使用请求 `safe_candidates` 中的 ID；可含 `reasons_by_id`、`modifications_by_id`，值为短字符串数组。
- `food_chat`: `reply` 字符串；可选 `proposal`。推荐结构为 `{meal_type,recipe_id}`，其中 `recipe_id` 必须来自请求 `context.safe_recipes`，服务端会重建食材、营养及估算价格；未设置单餐价格上限时，也接受 `{meal_type,items:[{name,grams,kcal,carb_g,protein_g,fat_g,allergens}]}` 自由方案。设置价格上限后，自由方案因无法核验价格而被拒绝。
- `workout_recovery`: 仅返回 `{ "advice_ids": ["protein", "carb", "water"] }` 这类 ID 列表，且每个 ID 必须来自请求的 `allowed_advice`；服务端不接受 Agent 新增建议文字、食材或剂量。
- `nutrition_diagnosis`: `observations` 为短字符串数组；`advice` 为对象数组，每项需有 `text` 和 1–5 个 `evidence_refs`（`{"period":"YYYY-MM-DD","metric":"net_kcal"}` 等引用输入 `series` 中实际存在的周期及指标）；可选 `confidence`（0–1）与 `model`（网关报告的模型标识）。缺失或伪造依据时整份 Agent 输出回退为本地规则；网关报告的模型名不是客户端独立验证的身份。

Agent 结果始终视为不可信输入：图片识别需用户确认；推荐只能重排服务器安全候选；对话方案在展示时校验数值、热量预算和饮食限制，确认预记入时再按最新账本、偏好和菜谱复核。已登记菜谱的食材与营养由服务端计算，模型填写的明细不会直接采用；若价格上限已配置，只有价格可核算且符合上限的菜谱可入账。有过敏或忌口配置时，未知食材会被拒绝；内置食材目录也无法验证餐厅真实配料或交叉接触，用户仍须核对。

识餐请求的 Base64 原图仅在内存中处理：服务端校验声明格式与真实解码格式一致、文件可完整解码、单帧及最多 800 万像素，再按方向信息旋转、最长边缩至 1600 像素并重新编码为无 EXIF 的 JPEG；只有重新编码的内容进入 Agent 网关。输入限制 1 KB–3.5 MB，输出也不超过 3.5 MB。无法解码、超尺寸或 MIME 不符时返回 400，且不建立识餐任务。客户端仍会先压缩和清除 EXIF；服务端重复校验是独立安全边界。图片像素和元数据不会写入服务端数据库，审计只保存哈希与结构化结果。

资讯抓取只接受 HTTPS 域名，拒绝跳转至白名单之外的地址、IP 字面量和不安全文章链接。抓取失败保留数据库中已有资讯；客户端仅缓存最近一次成功读取的公开资讯字段，并注明缓存时间。若 RSS 的文章或图片托管于另一域名，先审核该域名，再配置 `NUTRIPULSE_RSS_ALLOWED_HOSTS`。

文章默认可见、优先级为 0。持有 API 令牌的本机管理员可调用 `PATCH /api/v1/articles/{id}/moderation`，请求体为 `{"status":"VISIBLE"|"HIDDEN","priority":0..100}`；首页先按优先级、再按发布时间排序，最多显示 10 条。隐藏文章不会返回给客户端，但已离线缓存的旧文章只能在客户端下一次成功同步后更新。

## 关键接口

| 分类 | 接口 |
| --- | --- |
| 档案 | `GET/PUT /profile`，`POST /measurements`，`POST /goals/preview`，`POST /goals`，`PUT /preferences`，`PUT /training-profile` |
| 隐私 | `GET /privacy/export?category=...`，`GET /privacy/delete-preview?category=...`，`POST /privacy/delete` |
| 饮食 | `GET /nutrition/days/{date}`，`GET /foods?q=...`，`GET /foods/frequent`，`POST /meals`，`POST /meals/{id}`（状态），`POST /water-logs`，`POST /food-scans`，`POST /food-scans/{id}/confirm` |
| 健身 | `GET /training-plans`，`POST /training-plans/{id}/enroll`，`GET /training-plans/active?date=...`，`POST /training-plans/active/sessions/{id}/replace`，`POST /workouts/estimate`，`POST /workouts`，`GET /workouts/{id}/recovery`，`GET /fitness/days/{date}` |
| 设备 | `GET/POST /devices`，`POST /devices/{id}/samples`，`DELETE /devices/{id}?delete_history=false|true`，`GET /devices/conflicts`，`POST /devices/conflicts/{id}/resolve`；Android 端通过 Health Connect 授权读取后导入，不是手表厂商 OAuth |
| 决策 | `POST /recommendations/meals`，`POST /recommendations/{id}/accept`，`POST /recommendations/{id}/feedback`，`POST /agent/chats`，`POST /agent/chats/{id}/messages`，`POST /agent/chats/{id}/accept` |
| 统计/资讯 | `GET /analytics/energy`，`GET /analytics/macros`，`GET /analytics/habits`，`GET /analytics/body-composition`，`POST/GET /analytics/diagnostics`，`POST /reports`，`GET /articles` |
| 运维/配对 | `GET /health`，`GET /diagnostics/logs?limit=1..500`（鉴权、脱敏、仅当前进程），`POST /auth/pair`，管理员 `POST /auth/pair-code` |

路径均以 `/api/v1` 为前缀。手工餐食、运动、饮水新增和拍照识餐请求支持 `Idempotency-Key`：同一次保存的超时重试必须复用原键及原内容，成功后新建记录才使用新键；客户端表单在结果未明时不允许修改内容后复用旧键。推荐接受、对话方案接受和识餐确认按服务端业务对象保证并发/重试仅入账一次，不依赖客户端每次请求的随机键。计划餐不会计入真实摄入，确认吃过后才计入。

`GET /analytics/habits?start=YYYY-MM-DD&end=YYYY-MM-DD` 给出所选周期的饮水覆盖与目标达标日、已知膳食纤维克数和未知项数量、早午晚三餐记账覆盖，以及官方计划跟练完成数。纤维只汇总明确填报的已吃餐食，未填值不当作 0；计划餐不参与摄入。饮水达标只比较已经结束且确实记水、又有当日目标的日期；三餐与训练比例只用已结束日，分别至少有 3 个有效样本才提供百分比。今天的已记数据可见，但不纳入上述完成率。旧停练报名缺少实际停练日期时，对应排程保守排除并返回 `legacy_stop_unknown_sessions`，不把潜在停练后的日程当作失败。迁移 `020_plan_stop_date.sql` 为新停练或切换计划写入 `stopped_on`；历史日期不作猜测回填。PDF 报告采用同一周期和相同缺失值口径。升级前自动备份；回滚应停服后将迁移前一致快照恢复到新的数据库路径并切换 `NUTRIPULSE_DB`，不要直接删列或覆盖正式库。

`GET /analytics/body-composition?start=YYYY-MM-DD&end=YYYY-MM-DD` 逐周返回 `weight_kg`、`body_fat_pct` 与 `training_volume_kg`。同周多次测量分别取最新体重和最新非空体脂；无测量的周返回 `null` 而非沿用旧值。Android 把体重放在独立 kg 图中，避免和体脂百分比、训练容量共用坐标。PDF 报告版本 `analytics-pdf-v3` 的趋势表加入体重列。

推荐与对话方案已经入账后，重复确认返回同一餐食 ID 和账本中的**当前**状态（可能已从 `PLANNED` 变为 `CONSUMED`），不会再生成餐食。若该餐食已删除，重复确认返回 HTTP 409 `ALREADY_REMOVED`，需重新推荐或发起新对话；不会返回失效 ID。重复 `DELETE /meals/{id}` 成功且不再写第二条删除审计事件；原有 5 秒撤销窗口仍从第一次删除计时。

`GET /workouts/{id}/recovery` 读取已保存的训练组容量、时长、估算热量与对应日期的最新饮食/饮水账本，返回 `summary/evidence/advice/notices/source/reference`；无目标时缺口为 `null`，宏量不完整、历史回顾和估算热量均有边界提示。Android 在训练保存成功后立即请求并展示，获取建议失败也不回滚训练。未配置 Agent 时使用本地规则；配置 Agent 后也只允许从服务端给出的建议 ID 中选 1–3 项，无效响应回退规则，不将模型自造剂量或菜品展示为事实。规则参考面向健康运动成人的 [ISSN 2017 营养时机立场文件](https://pmc.ncbi.nlm.nih.gov/articles/PMC5596471/)；本 Demo 不根据单次运动估算自动增加饮食预算，也不提供诊断、治疗或个体化医学建议。此接口不新增迁移，回退时使用旧版本服务即可；真实 Agent 网关和真机弹窗尚待验收。

目标切换先调用只读的 `POST /goals/preview`，请求体为 `{"goal_type":"muscle_gain"}`；响应含当前/拟议 kcal 与宏量、计算输入、缺失字段和 `input_fingerprint`。确认时把该指纹原样传给 `POST /goals`，若档案、测量、现行目标或日期在此期间改变，服务端返回 409 并要求重新预览。未确认前原目标保持生效。新生成的营养目标保存输入快照、所用测量/目标 ID、档案版本和算法版本；旧目标的输入快照不可倒推，明确保留为空。迁移 `014_target_provenance.sql` 增加这些列，升级前自动备份。

`GET /recipes/{id}` 返回标准份的食材克数、步骤、估算价格，以及由食材营养值汇总的 `nutrition_per_serving`（`kcal/carb_g/protein_g/fat_g/fiber_g`）。客户端选择 0.5/1/1.5/2 份时按相同倍数展示食材、营养与价格；未知价格明确标为未知，不当作免费。数值为静态食材估算，并非餐厅实际成分；预记入时服务端仍重查最新饮食限制与当日预算。

`POST /recommendations/{id}/feedback` 接受 `{"feedback_type":"DISLIKE"|"REPEATED"|"UNSUITABLE"|"CLEAR"}`。每道菜只保留当前反馈，后续推荐按类型降权；反馈不删除安全候选，更不会自动改写过敏原或永久忌口。旧推荐会话的分数与顺序不回写。`POST /recommendations/meals` 带 `{"shuffle":true}` 时，先按同样的过敏、忌口、价格、时间和热量硬约束得到安全池，再只抽出一项；可用 `avoid_recipe_id` 请求“换一个”，有其他候选时不重复上一项。会话快照的 `blind_box` 保存候选清单、候选池指纹、抽中 ID 和时间。迁移 `016_recommendation_feedback.sql` 增加反馈表；反馈归属个人 Agent 数据，可分类导出与清空。升级前自动备份；如需回滚，停服后将迁移前一致备份恢复到新库路径并切换 `NUTRIPULSE_DB`，不要在运行中直接撤销表。

菜品排序在硬约束过滤后按 PRD 七项权重计算：营养缺口 0.35、热量 0.20、偏好 0.15、阶段 0.10、场景 0.10、多样性 0.05、历史反馈 0.05。场景已硬过滤，合格候选该项记 100；多样性依据近 7 天已预记或已吃的推荐菜品，最多降至 0；负反馈不影响过敏/忌口库，但在展示排序上置于未负反馈候选之后。无偏好、无目标等输入使用显式中性分，不虚构历史。会话快照保存七项权重、每个展示候选的分项得分及 `recommend-v3-weighted-<配置指纹>`，旧会话保留当时分数。调整权重后只影响新会话；如需回退，移除环境变量并重启服务，不涉及数据库迁移。分数仅用于 Demo 决策辅助，不代表医学上的营养适合度。

`GET /recipes/{id}` 对自煮菜谱额外返回 `substitutions`：仅从迁移 `017_food_substitutions.sql` 的人工维护关系中选取已核验、未触犯当前过敏/忌口的食材；替代克数按原食材热量近似等值计算，并返回替换后全餐每标准份的营养预览。`matches_current_restrictions=false` 表示原菜谱与最新档案冲突，应重新生成推荐。替换只是备餐参考，**不自动改写**推荐项或 `POST /recommendations/{id}/accept` 的计划餐；用户实际替换后须在饮食页修改明细并核对真实包装、过敏原、价格和烹饪方式。恢复旧版本时需停服，使用迁移前一致快照恢复到新库路径并切换 `NUTRIPULSE_DB`；不要直接删除替换表或覆盖正式库。

餐食的热量必填，碳水/蛋白质/脂肪/纤维可缺省。迁移 `015_nutrient_known_mask.sql` 为 `meal_items` 增加逐项已知位（1/2/4/8）；显式填写的 `0` 视为已知，未填写项仅为汇总计算存数值 `0`，同时保留未知标记。`GET /meals` 和常用食物接口返回该标记，整条餐食往返更新时也可原样提交以保留标记。日报返回 `incomplete_macro_items`，周期宏量报表返回 `incomplete_items`；占比只反映已知克数，不应解读为完整摄入。旧版记录无法可靠辨别零与缺失，升级后默认标记为未知，不倒推；升级前自动备份，回滚需停服恢复迁移前一致快照到新库路径。

`GET /training-plans` 默认返回全部六套已发布计划；可用 `level=beginner|intermediate|advanced` 与 `goal_type=fat_loss|maintenance|muscle_gain|recovery` 独立或组合筛选。非法筛选值返回 400，组合无匹配时返回空列表，不擅自放宽条件。Android 健身页默认展示全部计划，点击“只看适合我的”后使用个人页的训练水平和当前目标调用服务端筛选；个人训练水平为 `recovery` 时按初级训练水平筛选并在界面说明。当前跟练计划不受浏览筛选影响。

官方计划目录现为 v2，包含适用人群、风险提示、热身/冷身、进阶规则、替代动作、预计时长、完成标准和更完整的每日动作组次；PLAN-05 的 9 周模板区分积累、强化、减量与技术测试。迁移 `018_plan_catalog_details.sql` 增加计划说明字段和旧模板归档表，随后启动种子更新仅升级版本小于 2 的官方模板。已报名用户的 `plan_version` 和已生成的 `plan_session_instances.template_json` 是历史快照，不会被目录升级覆盖；更早期尚无实例的旧报名可按归档模板补建日程。重新报名才采用新版。迁移前自动备份；如需回滚，停服后恢复迁移前一致备份到新库路径并切换 `NUTRIPULSE_DB`，不要直接删列或覆盖正式库。

力量组支持二选一的 `reps` 或 `duration_sec`：计时组提交 `{"reps":0,"duration_sec":20}`，完成组必须有正数次数或秒数，不能同时提交两种非零目标。时长使用既有 `exercise_sets.duration_sec` 列，不需要新增迁移；计时组可记录外部负重但不计入 `重量×次数` 训练容量。官方计划中的“秒”动作按实记秒数判定完整/部分完成，不再把秒数冒充次数；历史旧记录保留原数据，不倒推时长。

设备活动热量若含有效 `start_at/end_at`，服务端按用户时区的自然日做时间窗结算；重叠时段默认设备优先，未重叠的手工训练仍可计入。已证明的设备—手工重叠进入 `GET /devices/conflicts` 队列，`POST /devices/conflicts/{id}/resolve` 可提交 `KEEP_DEVICE`（整笔手工训练热量不计）、`KEEP_MANUAL`（重叠时段用手工热量）或 `MERGE_NON_OVERLAPPING`（重叠用设备，手工仅计未重叠段）。训练容量和时长始终保留。处置后该日统计缓存立即失效；改动设备样本时间窗会使旧处置失效。旧版仅有每日合计的样本缺少可判定时间窗，继续按设备/手工日合计取较大值，日报 `activity_quality=daily_fallback`，不会虚构冲突。`activity_quality=time_window` 才表示区间结算。跨日活动样本需按用户时区拆分；跨日手工训练目前需分日录入。多设备提供商仍先按单日活动热量选择一处来源，不把多源总量相加。迁移 `013_activity_conflicts.sql` 增加冲突索引、重叠秒数和设备样本激活状态；升级前自动备份，回滚需停服后恢复迁移前备份到新库路径。

`GET /devices` 附带各连接的 `sample_count`。`DELETE /devices/{id}` 默认仅撤销服务端连接并保留原始样本；不能再导入，但该连接既有的活动热量、步数、心率、冲突处置和身体测量继续参与历史统计与目标计算。重新授权同一来源时会复用该连接和样本 ID，避免近 7 天数据重复入账。传入 `delete_history=true` 会永久删除该连接的样本、冲突、关联身体测量和由这些测量生成的目标，同时清除旧 AI 诊断并尝试使用剩余测量重算当前目标；若没有可用测量，当前目标为空。该接口可再次调用以清除先前保留的已撤销连接历史，不影响其他连接或手工账本；响应包含删除数量与目标重算状态。旧导出文件和 Health Connect 自身的数据不会随服务端删除而消失。Android 客户端撤销 Health Connect 时另行关闭自动同步并尝试撤回系统健康权限；若系统撤权失败，会提示用户在系统设置中处理。

兼容旧版曾为同一来源建立多个连接的数据库：统计和冲突队列按 `provider + sample_type + external_id` 只选一份有效样本，优先已完成同步的活动样本，再优先当前有效连接与较新连接。原始重复行仍可导出；跨日更正、删除或切换获选副本会使相关日期统计缓存和冲突状态重新计算。迁移 `019_device_external_lookup.sql` 只增加外部样本 ID 查询索引，不改写已有健康记录；启动时先做迁移前一致备份。如需回滚，停服后恢复该备份到新库路径并切换 `NUTRIPULSE_DB`，不要在运行中覆盖原库。

Health Connect 客户端以单条活动能量区间同步，不再只传每日合计；跨午夜记录按区间时长比例分日，最多 500 条/批。批次提供 `sync_batch_id` 与 `stage_active_energy=true`；最后一批附 `activate_active_dates`，服务端在单一事务中激活本批区间样本、停用该日期旧合计及已从 Health Connect 删除的旧区间样本。失败在最终激活前不会把新旧两套活动数据相加；重复提交同一批的外部样本 ID 不重复入账。撤销但保留历史不会改变已归集数据；删除历史时，相关日期与冲突队列重新计算。当前固定使用个人 Demo 的上海时区；未来支持编辑时区时需同步调整客户端分日规则。

识餐上传中的重复请求返回同一任务的 `PROCESSING` 状态，不重复调用 Agent；稍后以同一照片和重试键再次提交可取回结果。Agent 调用失败后同键可重试，服务异常中断而遗留的 `PROCESSING` 任务在 120 秒后可重新认领；旧调用即使迟到也不能覆盖新结果。客户端选择保存照片草稿时会加密保存照片，并保留该次操作键；删除草稿一并删除重试键。相同键用于另一张照片会返回 409。迁移 `011_food_scan_retries.sql` 增加任务的幂等键、输入指纹、尝试标识和开始时间；升级前自动备份，回滚需停服后恢复迁移前备份到新库路径。照片本体仍不在服务端落盘。

`POST /food-scans/{id}/confirm` 可省略 `items`，此时采用待核对的识别项；显式提供 `items` 时只使用用户提交的复核结果。若 `items=[]` 或 `null`，返回 400 且不写餐食，绝不会回退为原始 AI 识别项。手工补充项可以只提供热量，不明的宏量按未知标记；日报和周期统计会提示不完整。

运动录入的预估接口为 `POST /workouts/estimate`，例如 `{"workout_type":"cycling","intensity":"moderate","minutes":30}`；返回 `kcal/met_value/weight_kg/weight_source/calculation_version`，不写入账本。项目支持步行、跑步、骑行、游泳、瑜伽和力量训练，强度可选 `low/moderate/high`，对应服务端 `app/domain/exercise.py` 中的版本化 Demo MET 参考表；统一按 `MET × 3.5 × 体重kg ÷ 200 × 分钟` 计算。未录入体重时明确标记 `demo_default` 并暂用 70 kg，不将其称为个人精确值。`POST /workouts` 用同一计算函数重新结算，保存实际 MET、强度、来源和 `met-demo-v1`；手工填写热量则保存 `MANUAL/manual-v1`。旧记录标记 `legacy-unversioned`，不伪称可追溯。`PUT /training-profile` 可配置每日活动热量目标 `active_kcal_goal`（50–2000，默认 300）；健身日报返回目标、已完成分钟数、力量估算、设备与手工活动值及来源/同步时间，最近心率另带样本来源与采样时间，无样本不虚构实时心率。迁移 `012_fitness_estimation.sql` 加入这些字段；升级前自动备份，回滚需停服后恢复迁移前备份到新库路径。MET 是粗估，训练容量仍单独记录；设备与手工的区间结算及旧数据回退规则见上文。

`POST /workouts` 的力量组允许 `weight_kg: null` 或省略，表示自重动作；次数、完成状态和可选 RPE/RIR 照常保存。自重组的外部负重容量计 0，不把个人体重虚构为器械重量；混合训练只汇总有明确重量且已完成的组。已完成组必须有大于 0 的次数。Android 按组表单将空白重量发为 `null`，用户可继续跟练恢复回归等自重计划。

`POST /analytics/diagnostics` 每次生成新版本，保存所选区间的统计输入快照、SHA-256 指纹、模型/提示词版本、生成时间和建议引用的指标；响应包含报告 `id/version`。`GET /analytics/diagnostics?start=YYYY-MM-DD&end=YYYY-MM-DD` 返回该区间最近 20 个版本（新到旧）。若 Agent 未配置、失败或依据不合法，会生成并保存本地规则版；`confidence=null` 表示无法可靠评估，不得解释为低置信度。迁移 `007_diagnostic_provenance.sql` 增加来源元数据和查询索引；启动前自动备份，回滚需停服后恢复迁移前备份到新库路径。

年/月能量与宏量报表先读取 `daily_energy_snapshots` 日快照；缺失日期才按账本类型做固定次数的区间聚合，再逐日应用与 `GET /analytics/days` 相同的能量公式并写入快照。宏量原值保留在 `macro_json`，能量与训练容量原值保留在 `raw_json`，跨日汇总先求和再舍入。迁移 `008_analytics_range_indexes.sql` 补充饮水索引，`009_energy_snapshot_invalidation.sql` 扩展快照字段，`010_energy_raw_precision.sql` 保存原始精度；数据库触发器在餐食、饮水、训练、设备样本与目标变更时按受影响日期清除缓存，设备连接撤销时清除该用户缓存。事务回滚同时回滚失效操作。回滚迁移需停服并恢复自动生成的迁移前备份到新库路径。

可在 `server/` 执行 `python tools/benchmark_analytics.py --runs 5`；脚本只在系统临时目录生成合成库，不读取正式数据库，并分别报告首次重算与缓存命中。2026-10-03 本机单进程测试：20 万餐食明细、10 万训练组、5 万设备样本时，367 天能量报表冷查询 143.1 ms、5 次热查询 P95 11.6 ms；宏量报表冷查询 84.4 ms、热查询 P95 10.4 ms。10 倍数据量（200 万/100 万/50 万）时，367 天能量报表冷查询 1153.1 ms、3 次热查询 P95 12.9 ms；宏量报表冷查询 991.4 ms、热查询 P95 9.1 ms。少量合成样本不代表并发、弱磁盘、冷启动或不同设备上的正式 SLA；体脂趋势查询尚未使用此快照。

训练计划启用时以请求 `start_date` 为第 1 周第 1 天，每 7 天为一周，将官方 `plan_days` 展开为个人 `plan_session_instances`；未安排动作的日期为休息日。`GET /training-plans/active?date=YYYY-MM-DD` 及 `GET /fitness/days/{date}` 的 `active_plan` 提供 `progress`、`today_session`、`next_session`、`week_sessions`；每次实例含原始及有效动作，有氧实例附 `minimum_duration_minutes`。按组或按时长结束训练时，`POST /workouts` 提交 `plan_session_id`，服务端校验报名仍有效、日期匹配、实例未结束，并原子更新训练记录与进度；同一实例不允许第二笔训练重复计入。力量计划只有各动作的规定组数及每组最低次数均实际完成才标记 `COMPLETED`；提前结束、次数不足或仅按时长记录为 `PARTIAL`。有氧/间歇计划达到模板最短时长才算完整完成；`progress.completed` 和 `progress.partial` 分开展示，不夸大完成率。动作替换接口示例为 `{"index":0,"replacement":"哑铃卧推 4×8","reason":"器械条件调整"}`，只改个人当次实例，保留替换原因和历史；官方计划模板不变。带组数的计划训练若提交了未在有效动作中的名称，会被拒绝并提示先登记替换。迁移 `005_plan_sessions.sql` 增加计划日实例与唯一会话关联；升级前自动创建 `pre-migration` 备份。若需回滚，停服后将 `NUTRIPULSE_DB` 指向该备份恢复的新库路径，再启动旧版本服务；不要在运行中改写现有数据库。

`POST /reports` 请求示例：`{"period":"week","end":"2026-10-03"}`，周期可选 `day/week/month/year`，截止日期为 `YYYY-MM-DD`。响应是 `application/pdf` 二进制文件，不采用普通 JSON 数据包；仍需 Bearer 令牌，并设置 `Cache-Control: no-store`。导出内容与数据页当前筛选周期一致，体脂/容量对照图为与数据页相同的最近 8 周。报告只在内存中生成，服务端不留存副本；用户在 Android 系统文件选择器中确认保存位置。报告使用规则分析，不会为 PDF 额外请求联网 Agent。无有效代谢目标的周期不虚构消耗和净差。生成时若未安装 ReportLab 或没有可嵌入的中文字体，会返回可读的 503 错误。

`GET /foods/frequent` 仅从未删除且已确认食用的餐食明细中按食物 ID/名称聚合，最多返回 10 项；每项包含最近一次实记的份量、单位、可选克数、热量和宏量，以及使用次数。`ml`/`份`/`个` 如无可靠换算，`grams` 保持 `null`，不会假定 1 ml 或 1 份等于 1 g。`GET /analytics/days?date=...` 还返回只读步数及 `steps_source`/`steps_synced_at`；无设备样本时来源与时间为 `null`。Android 饮食页允许查看历史日期，日期选择器可预记到未来 90 天；此限制是 UI 交互范围，服务端日期 API 仍可查询更久以前的合法历史记录。

`PUT /preferences` 可额外提交 `dining`：`max_cost_cny`（可省略，1–1000）、`max_cook_minutes`（可省略，5–240 的整数）、`flavors`（清淡/咸鲜/甜口/香辣）和 `preferred_scenario`（self_cook/takeout/dine_in/convenience）。`GET /profile` 返回同一结构。推荐先按已确认过敏原、忌口、营养预算、估算单餐费用过滤；自煮还按备餐+烹饪分钟数过滤，再按营养和口味排序。接受推荐时按选择的份数重新校验费用和最新偏好，超出则返回 `HARD_CONSTRAINT_VIOLATION`。预算价格为静态 Demo 估算值，并非实时价格或商家报价；若设置费用上限，未知价格的候选不会通过过滤。没有安全候选时返回空列表，不自动放宽硬约束。迁移 `004_dining_preferences.sql` 为既有数据库增加独立用餐偏好表及菜谱元数据列；启动时内置菜谱会回填 Demo 估算数据。回滚前应停服并备份数据库；SQLite 不支持无损直接撤销新增列，需迁移到新库并重建旧表结构。

隐私接口的 `category` 可选 `all`、`diet`、`fitness`、`agent`、`profile`。导出返回可读 JSON；分类导出会包含该类别清空时连带移除的推荐、诊断等记录，方便先备份。服务端 `POST /privacy/delete` 必须提交 `{"category":"diet","confirmation_phrase":"DELETE_DIET"}` 形式的精确确认短语；先调预览接口查看记录数量和影响。`diet` 清账本及相关 AI，`fitness` 清运动/设备及相关 AI，`agent` 清推荐/对话/识餐及诊断但保留账本，`profile` 重置档案/目标并断开设备但保留账本，`all` 清除个人记录并恢复空白档案。服务端清空不可撤销；旧备份、已导出的 JSON 和系统外部 Health Connect 原始数据不随之删除。Android 端执行 `fitness`/`profile`/`all` 清空前会阻止新的健康数据同步，成功后关闭自动同步并尝试撤销本应用的 Health Connect 系统权限；若系统撤权失败，需在系统设置中手动处理。当前服务端不落盘保存原始识餐照片，Android 加密照片草稿由客户端在清空 `diet`/`agent`/`all` 成功后本地删除；若未来启用服务端文件持久化，必须同步实现二进制文件清理。`all` 还会清除客户端保存的访问令牌，需要重新配置连接。清空前建议停服备份 SQLite；恢复时停服，将备份数据库及 WAL/SHM 一致性文件恢复，或使用 SQLite 在线备份生成的完整副本。

## 验证与备份

`python -m unittest discover -s tests -v` 运行服务端单元/集成测试。服务启动后会立即通过 SQLite 在线备份 API 创建当前上海日期的日备份和本 ISO 周的周备份，之后每小时检查一次；相同日/周不重复生成，分别最多保留 7/4 份。迁移已有数据库前会额外生成 `pre-migration` 快照；如果备份失败，迁移中止。手工和迁移前备份不受自动轮换影响。备份都带 JSON 清单，记录 SHA-256、数据库完整性/外键检查通过后的表计数与迁移版本。SQLite 处于 WAL 模式时**不能**只复制运行中的主 `.sqlite3` 文件。

在 `server/` 下可运行：

```powershell
python tools/db_backup.py create
python tools/db_backup.py verify 'data/backups/nutripulse-manual-<时间戳>.sqlite3'
python tools/db_backup.py restore 'data/backups/nutripulse-manual-<时间戳>.sqlite3' 'data/restored.sqlite3'
```

恢复命令先校验备份，再写入**不存在**的新数据库路径，拒绝覆盖现有数据库及已有 WAL/SHM 文件；恢复后再次核对哈希、表计数、迁移版本和 SQLite 完整性。正式切换时先停服，保留原库及 WAL/SHM 文件，将 `NUTRIPULSE_DB` 指向新路径并启动服务，核对健康检查与关键记录；若不符，停服后重新指向原库即可回滚。不要在服务运行时直接复制/替换数据库。备份和 JSON 导出均包含明文个人健康数据，请将备份目录放在仅本人可访问的位置，不要上传公开网盘；当前 Demo 尚未实现加密备份。

执行 `python tools/generate_sample_report.py` 可用临时合成数据库生成一份非个人数据的 PDF 样例于 `../output/pdf/NutriPulse_analytics_sample.pdf`，用于检查 A4 排版与中文字体；脚本不会读取或改写正式数据库。
