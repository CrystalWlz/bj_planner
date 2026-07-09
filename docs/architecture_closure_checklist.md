# 架构收口清单

更新时间：2026-07-09

总体结论：当前大架构目标处于“关键地基已落地，整体尚未完成”的阶段。以下清单用于判断何时可以把“数据库核心对象表、统一 planning_goals、多目标顺序规划、政策接口解耦、前端概念统一、缓存分层”标记为完成。

## 状态口径

- 已收口：实现、数据流、测试护栏和文档都已有稳定落点。
- 部分收口：主链路可用，但仍有兼容结构、页面差异、测试缺口或迁移尾巴。
- 待收口：还没有统一真源，或没有形成可验证的工程护栏。

## 1. 数据库核心对象表

状态：已收口

当前证据：

- `backend/app/database.py` 已有 `core_objects` 表、分类索引和 owner 索引。
- `backend/app/core_objects.py` 已派生现金、投资、公积金、养老医保、贷款、目标资产、规划贷款和账户校准记录。
- `backend/app/planning_context.py` 已把 `core_objects` 纳入 `CalculationContextSnapshot`。
- `backend/tests/test_api.py` 已覆盖核心对象派生、owner 过滤、禁用/暂不纳入目标排除、全局目标同步和账户校准记录。

收口条件：

- [x] `core_objects` 表存在，并有 household/type/category/owner 维度索引。
- [x] 目标资产和规划贷款的 `owner_key` 稳定指向 `planning_goal_id`。
- [x] `not_planned` 或 disabled 目标不派生本次规划资产和贷款。
- [x] 账户校准记录保留 `calibration_scope`、`source_id`、`source_category`、`source_title`、`reference_name`。
- [x] 前端所有需要解释账户、资产、贷款、校准来源的页面都优先消费统一核心对象/概念，而不是各自拼旧字段。
- [x] 导出、可视化、记账校准、策略解释对核心对象的展示口径做一次一致性验收。

补充证据：

- 家庭财务、记账校准、理财和可视化页通过 `coreObjects.ts` helper 消费 `account_concepts` / `core_object_groups`。
- 可视化页新增“核心对象口径”摘要，账户、资产、贷款说明与家庭财务、记账校准和导出表共用后端概念。
- 策略解释由 `build_strategy_explanations(..., account_concepts, core_object_groups)` 注入核心对象摘要，导出策略解释复用同一字段。
- `backend/tests/test_api.py::test_frontend_visualization_and_strategy_explanations_share_core_object_concepts` 与 `backend/tests/test_calculator.py::test_affordability_returns_backend_strategy_events_and_concepts` 覆盖一致性验收。

## 2. 统一 planning_goals

状态：已收口

当前证据：

- `backend/app/database.py` 已有 `planning_goals` 表和 API 映射。
- 房源、车辆、养娃目标已有从旧页面结构投影/保存到 `planning_goals` 的路径。
- `backend/app/planning_context.py` 会读取统一目标并应用到本次计算请求。
- `frontend/src/planningGoals.ts` 已集中维护目标类型、顺序标签、目标纳入规划判断和旧页面投影。
- 购房、购车、养娃目标已覆盖新增、复制、删除、启用/停用和选择策略写回；养娃复制目标通过 `createPlanningGoal(childPlanningGoalData(...))` 创建新的统一目标，不再只复制本地 `child_plans` 数组。
- 统一目标列表端到端测试覆盖同一家庭买房、买车、养娃目标的列表完整性、顺序依赖稳定、跨家庭隔离、`planning-foundation` 一致性，以及 raw household shadow 列表不被投影目标污染。
- `/api/planning-goals` 创建/更新购房目标不再写旧 `scenarios` shadow；旧 `/api/scenarios` 读路径仍从 home `planning_goals` 投影，旧兼容写路径保留但不再作为统一目标 CRUD 的第二真源。
- 前端新增“规划目标”页，装修/其它目标可通过统一目标库新增、复制、删除、启用/停用、编辑预算和顺序；静态测试覆盖该页使用横向目标卡片并调用 `createPlanningGoal`、`savePlanningGoal`、`deletePlanningGoal`。

收口条件：

- [x] 买房、买车、养娃进入同一张 `planning_goals` 主数据表。
- [x] 前端保存房源和车辆目标时按目标列表写回，而不是只保存当前选中项。
- [x] `target_params` 清理旧的顺序、策略选择和政策真源字段。
- [x] 旧 household/scenario/car/child shadow 结构只作为兼容投影，不再形成第二套业务真源。
- [x] 购房、购车、养娃、装修/其它目标的新增、复制、删除、启用/停用、选择策略交互完全复用统一语义。（装修/其它目标先通过通用“规划目标”页管理统一目标；专属策略生成后续继续落同一目标。）
- [x] 统一目标 API 与前端目标列表做一次端到端验收，确认没有目标丢失、顺序抖动或跨家庭复制影子目标。

## 3. 多目标顺序规划

状态：已收口

当前证据：

- `backend/app/domain/planning_goals.py` 已解析自动排队、并行、手动时间、跟随目标、等待月份和规划窗口。
- `backend/app/events.py` 会把目标顺序转换为统一规划目标事件。
- 测试已覆盖并行目标不占用 `sequence_index`、显式依赖并行目标可作为锚点、禁用/暂不纳入目标降级 warning。

收口条件：

- [x] 顺序解析层是统一入口，页面不各自解释“第一套/第一辆”。
- [x] 并行目标不挤占后续自动顺序目标。
- [x] 手动指定时间和 after_goal 依赖能进入计算上下文与事件线。
- [x] 策略生成、账本、可视化、导出全部只消费解析后的统一顺序结果。
- [x] 端到端验证混合场景：买房 + 买车 + 养娃 + 一个并行目标 + 一个跟随目标。

补充证据：

- `calculation_context` 已在 `build_affordability_result` 阶段进入结果对象，导出表不再等 API 层后置补写上下文。
- 导出新增“统一规划顺序”表，直接消费 `calculation_context.planning_goals` 的解析结果。
- `backend/tests/test_api.py::test_affordability_outputs_consume_resolved_planning_sequence` 验证同一解析顺序贯穿购车策略、养娃策略、月度可视化、月度账本和导出表。

## 4. 政策接口继续解耦

状态：已收口

当前证据：

- `backend/app/policies.py` 是城市政策包入口。
- `backend/app/engine_config.py` 承接运行时执行配置，避免把并行 worker 等性能参数混入政策包。
- 测试已增加护栏，限制除 `policies.py` 和 `engine_config.py` 外的后端模块直接读 `RulePackData.params`。
- 车辆、住房、税务、公积金等领域模块已大量通过 `get_policy(rules)` 访问政策。

收口条件：

- [x] 政策规则通过 `policies.py` 接口读取。
- [x] 执行配置从政策业务规则中剥离。
- [x] 有静态测试防止散落读取 `rules.params`。
- [x] 前端政策页只编辑规则包参数，不承担政策计算或推导。
- [x] 北京政策说明中的“政策来源、用户配置、市场假设”三类来源在购房、购车、税务、公积金说明中统一标注。
- [x] 后端新增政策字段必须同时补 schema、默认值、政策接口和测试，避免重新变成裸 `params.get`。

补充证据：

- `backend/app/policy_explanations.py` 统一提供“政策来源 / 用户配置 / 市场假设”说明标签。
- 购房策略描述、购车 `policy_notes`、税务策略时间线、公积金提取说明已复用同一组标签。
- `backend/tests/test_calculator.py::test_policy_explanations_label_sources_across_home_vehicle_tax_and_provident` 覆盖购房、购车、税务、公积金四类说明面。

## 5. 缓存分层

状态：已收口

当前证据：

- `backend/app/cache.py` 已定义 `input`、`strategy`、`ledger`、`visualization`、`engine` 五层 hash。
- `calculation_cache` 和 `generated_strategies` 已持久化 `engine_fingerprint` 与四个业务层 hash。
- `generated_strategies` 已支持按多层 hash 批量查询，并默认只返回当前 engine 指纹结果。
- `backend/tests/test_api.py` 已覆盖 cache layer 存储、命中回填、执行配置不改变业务缓存、按层查询策略实体。

收口条件：

- [x] 计算结果返回 `cache_layers`。
- [x] 缓存表和策略实体表持久化分层 hash。
- [x] 策略实体查询按 `engine + input + strategy + ledger + visualization` 定位。
- [x] 执行调度参数不制造业务缓存变化。
- [x] 每个层的代码路径归属再审一遍，确认新增模块没有漏进错误层。
- [x] 对 `core_object_concepts.py` 这类同时影响输入语义和展示语义的文件保留明确测试。

## 6. 生成策略实体

状态：已收口

当前证据：

- 后端已有 `generated_strategies` 表、owner key、strategy type、cache layer 字段和列表接口。
- 前端 `frontend/src/generatedStrategies.ts` 集中维护策略类型和 payload 解析。
- 购房、购车、理财、养娃、税务页面已有从策略实体读取的路径。
- 购房策略选择会通过 `selected_purchase_plan_variant` 写回统一购房目标 `selected_strategy_id`；购车策略选择会同步保存对应车辆 `planning_goals.selected_strategy_id`，不再只停留在本地 `car_plan` 临时状态。
- 养娃策略的推荐出生月可在页面中采用，并通过 `updateChildPlanPatch` 写回 `planned_birth_month`、出生窗口和统一养娃目标配置；实际出生月 `birth_month` 不会被策略采用动作误写。
- 理财策略采用会写回 `investment_plan_name`、风险等级、月定投、安全垫、资产比例、自动再平衡和年化收益，形成统一手动策略配置。
- 税务策略不是单一“采用方案”模型；子女扣除归属写回养娃目标 `tax_deduction_owner`，专项附加扣除写回 `special_deductions`，理财税务口径写回 `investment_tax_profile` 与简化税率字段。

收口条件：

- [x] 策略实体能从完整计算结果拆出并持久化。
- [x] 前后端策略类型集合有一致性测试。
- [x] 每个业务页都优先消费策略实体，不再直接遍历完整计算结果中的旧列表。
- [x] 策略 owner 匹配统一使用 `planning_goal_id`，legacy owner key 只做过渡回退。
- [x] 选择策略后能稳定写回统一目标或统一手动策略配置，而不是只在前端临时显示。（购房、购车、养娃写回统一目标；理财、税务写回统一手动策略配置。）

## 7. 前端概念统一

状态：已收口

当前证据：

- `PlannerPageShell`、`PanelTitle`、可折叠面板、目标卡片和策略主面板等基础组件已经存在。
- `frontend/src/planningGoals.ts`、`frontend/src/coreObjects.ts`、`frontend/src/generatedStrategies.ts` 已承接统一目标、核心对象和策略实体概念。
- 购车页已把“政策与上牌”调整为平行于“车辆参数与手动策略”的用车需求级模块。
- 记账校准页已能面向账户概念、重大事件和策略事件选择校准来源。
- 记账校准页从策略实体添加校准时，默认展示业务策略名称和来源说明，不再把 `strategy_key` 或 `owner_key` 暴露为用户备注。
- 月度可视化序列由 `frontend/src/visualizationSeries.ts` 只映射后端 `monthly_cashflow_visualization`、贷款、公积金和养老医保序列；测试禁止 `calculatedMonthlySeries`、`localMonthlyProjection`、`simulateMonthly` 等旧本地推演入口回流。
- “规划目标”页已承接装修/其它目标的统一目标卡片、当前配置、策略说明与影响预览。
- “导出方案”页已调整为导出对象横向卡片 -> 当前选中项配置 -> 策略说明 -> 影响预览与导出的统一骨架，并将兜底文案改为业务概念，避免出现内部字段名或旧模型名称。
- 前端策略来源标签已从“后端策略实体/计算响应”改为“策略库方案/本次计算结果”；记账校准策略来源也改为“来自策略库中的方案”，不再暴露 `strategy_key`、`owner_key` 或实现层来源名。
- 家庭财务、规划目标、购房、购车、理财、养娃、税务、政策、可视化、记账校准和导出页均已接入 `PlannerPageShell`，统一标题、摘要和顶部操作入口。
- 买房、买车、养娃、理财和导出页的目标/方案选择区均使用横向卡片类；典型内部实现文案（如后端策略实体、计算响应、后端字段名、后端并行工作数）已由业务文案替代。
- 家庭财务、规划目标、购房、购车、理财、养娃、税务、政策、可视化均通过统一工作流静态验收；养娃页目标选择已统一为“目标列表”，税务页自动动作统一为“自动策略”，购房页手动调整统一为“手动参数”。

收口条件：

- [x] 页面级壳统一支持标题、摘要、顶部说明和工具区。
- [x] 购车政策与上牌不再挂在每个车源下。
- [x] 记账校准来源覆盖账户概念、重大事件和策略事件。
- [x] 家庭财务、购房、购车、理财、养娃、税务、政策、可视化都符合统一工作流：顶部摘要 -> 目标/方案列表 -> 当前选中项配置 -> 策略说明 -> 影响预览。
- [x] 横向目标/方案卡片成为买房、买车、养娃、理财和导出的统一选择模式。
- [x] 页面说明文案统一使用业务概念，不暴露后端字段名或旧模型名称。
- [x] 前端不再保留旧本地推演或展示 fallback 作为业务计算来源。

补充证据：

- `backend/tests/test_api.py::test_generic_planning_goal_page_manages_renovation_and_other_goals` 覆盖通用规划目标页的统一目标卡片、装修/其它目标 CRUD 和统一目标 API。
- `backend/tests/test_api.py::test_export_page_uses_unified_workflow_and_business_copy` 覆盖导出页统一工作流、横向卡片和业务化兜底文案。
- `backend/tests/test_api.py::test_business_pages_prefer_generated_strategy_entities` 与 `test_account_calibration_page_uses_full_source_catalogs` 覆盖策略库优先、业务化来源标签和旧内部文案禁回流。
- `backend/tests/test_api.py::test_business_pages_use_planner_page_shell` 覆盖主要业务页统一使用页面壳和摘要。
- `backend/tests/test_api.py::test_business_pages_use_horizontal_selection_cards_and_business_copy` 覆盖买房、买车、养娃、理财、导出横向选择卡片，以及典型内部实现文案禁回流。
- `backend/tests/test_api.py::test_business_pages_expose_unified_workflow_sections` 覆盖家庭财务、规划目标、养娃、税务、理财、购房、购车、政策和可视化页的统一工作流段落。
- `backend/tests/test_api.py::test_affordability_api_projects_baseline_visualization_without_child_or_vehicle_plans` 与 `backend/tests/test_calculator.py::test_no_child_or_vehicle_plan_still_projects_baseline_visualization` 覆盖无养娃目标、无买车目标时仍生成“家庭基线”可视化、账本、账户快照和年度摘要。

## 8. 模块配置折叠

状态：已收口

当前证据：

- `PanelTitle` 和 `FormPanel` 支持 collapsible。
- 家庭财务、购房、购车、理财、养娃、税务、政策等页面已有一批可折叠面板或 details 面板。
- 政策页规则分类已调整为第一组核心规则默认展开，其余详细规则默认收起。
- `COLLAPSE_DEFAULTS` 统一定义 `core`、`advanced`、`explanation`、`longList` 的默认展开/收起规则，`WorkflowSection`、`CollapsiblePanel`、`CollapsibleSettingGroup` 共用 profile。

收口条件：

- [x] 基础折叠组件存在。
- [x] 大部分复杂配置区已开始使用折叠标题。
- [x] 各大模块的详细配置默认展开/收起规则统一：核心输入默认展开，进阶/解释/长列表默认收起。
- [x] 折叠状态不影响表单状态、计算触发和移动端可访问性。
- [x] 可视化页的大段解释与细节表统一使用可折叠详情，避免首屏过载。

补充证据：

- `WorkflowSection`、`CollapsiblePanel`、`CollapsibleSettingGroup` 均使用按钮、`aria-expanded` 和组件内 `open` 状态控制内容挂载，不改变外层表单数据。
- 可视化页顾问依据、归因解释、年度税务明细和本月财务解释使用 `<details>` 折叠。
- `backend/tests/test_api.py::test_collapsible_sections_keep_accessible_state_and_visualization_details_collapsed` 覆盖折叠组件状态与可视化 details 面板。
- `backend/tests/test_api.py::test_collapsible_default_profiles_are_centralized` 覆盖核心输入展开、进阶/解释/长列表收起的统一 profile 规则。

## 9. 记账校准统一

状态：已收口

当前证据：

- schema 已支持 `account`、`concept`、`major_event`、`strategy_event` 四类校准 scope。
- 账本投影层会按月份应用账户校准偏移。
- 核心对象记录保留校准来源元数据。
- 校准事件通过 `PlanEventPoint.calibration_source` 暴露结构化来源；可视化事件线和导出“关键事件时间线”共用该字段展示同一套来源。
- 记账校准页会提示停用校准不会进入后端账本和事件线、同月同对象多条启用校准的应用顺序风险，以及同来源重复启用校准。

收口条件：

- [x] 校准可以绑定到账户、账户概念、重大事件和策略事件。
- [x] 校准落到账本偏移，不绕过账本直接改展示。
- [x] 核心对象可追溯校准来源。
- [x] 前端校准页对所有来源都有清晰搜索/筛选和来源摘要。
- [x] 校准导出、事件线、账户曲线说明都能显示同一套校准来源。
- [x] 重复校准、禁用校准、同月多项校准的冲突提示完成验收。

## 10. 后端计算速度

状态：已收口

当前证据：

- `engine_config.py` 已把并行 worker 等执行配置从业务政策中拆出。
- 缓存分层能减少策略实体和完整计算误失效。
- 投影上下文缓存、策略管线和账本管线已有拆分。
- `backend/app/profiling.py` 已提供默认关闭的 `HOUSE_PLANNER_PROFILE=1` 后端 profile 开关，覆盖缓存、策略生成、账本投影、可视化和响应组装等阶段。
- `scripts/perf_calculation_sample.py` 已提供临时数据库下的固定冷启动/缓存命中性能样例，输出总耗时、cache layer、策略数量和月度账本行数。

收口条件：

- [x] 执行配置不污染业务缓存。
- [x] 计算缓存和策略实体缓存能按层复用。
- [x] 建立固定性能样例，记录冷启动、缓存命中、策略生成、账本投影、响应组装耗时。
- [x] 关键耗时路径有日志或 profile 开关，默认不污染用户界面。
- [x] 优化后用同一输入对比结果一致性，避免为了速度改变业务结果。

## 11. 发布与验证

状态：已收口

当前证据：

- 当前工作区仍有未提交修改。
- 当前收口阶段已跑完整后端测试、前端构建、编码扫描和隐私扫描；隐私扫描发现的测试夹具远期年月已移除，并补跑对应局部测试。
- 本轮完整后端测试耗时较长，后续小改应继续按“小改局部、大改阶段性全量”的节奏执行。

收口条件：

- [x] 当前未提交改动全部完成自查，并确认没有混入无关改动。
- [x] 中文文件修改后通过 `python scripts/encoding_scan.py`。
- [x] 涉及 Git 提交/推送前通过 `python scripts/privacy_scan.py`。
- [x] 后端至少跑 `python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py -q`。
- [x] 前端跑 `npm run build`。
- [x] 对桌面和移动端关键页面做一次浏览器检查：购房、购车、记账校准、可视化、政策页。Browser runtime 未暴露 `node_repl js` 工具，本轮使用 Playwright CLI + Microsoft Edge fallback；桌面检查了家庭财务、购车、记账校准、政策规则、可视化，移动检查了记账校准首屏与来源筛选区，唯一 console error 为 `favicon.ico` 404。

## 完成判定

只有当以下条件同时满足时，才能把这条大目标标记为完成：

- [x] `planning_goals` 是重大消费目标唯一主数据，旧 shadow 结构只剩兼容投影。
- [x] `core_objects` 是账户、资产、贷款、校准解释的统一索引。
- [x] 多目标顺序解析结果贯穿策略、账本、事件、可视化和导出。
- [x] 政策计算只通过政策接口，运行时配置与业务政策分离。
- [x] 缓存按分层 hash 稳定命中，并能解释失效来源。
- [x] 前端各业务页使用统一概念、统一骨架和统一目标/策略选择方式。
- [x] 局部测试、完整后端测试、前端构建、编码扫描和隐私扫描全部通过。
