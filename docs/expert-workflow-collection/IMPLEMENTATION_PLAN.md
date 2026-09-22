# 实现计划

对应 `PRD.md` v0.5。这份文档是从 PRD 到代码的桥梁：技术选型、目录结构、阶段划分、每个阶段的"完成"标准。PRD 是产品需求的权威来源，这份文档只管"怎么按顺序把它建出来"。

---

## 1. PRD 完备性审查结论

在动手写代码前，对着整份 PRD（第 0～18 节）和本仓库其余讨论过一遍，结论：

**可以开始实现**，理由：
- 专家采集层（第 1～10 节）：页面结构、数据模型、采集原则、Validator 规则、API 草案齐全
- 第 7 节两处设计冲突已裁定（DAG-only + retry_semantics；node 类型集合），`schema/` 已同步修订
- 视觉规范齐全且有参考原型：DAG（11）、Dashboard（13.7）、实验中心（14.7）、会话气泡（18.5）
- LLM 使用清单（15）+ 分类口径（15.0）+ 设置页设计（17）齐全，实现时不用现场再判断"这里要不要接模型"
- 数据源/数据集/方法/模型这几个容易混淆的概念已在 12.0、14.1 明确定义

**实现前仍需要记录的假设**（PRD 没有强制要求、但代码必须选一个具体值才能跑起来的地方，选择依据写在这里，不算擅自变更需求）：
1. **认证**：PRD 定义了角色（专家/研究员/管理员，16.2）但没有设计登录页——MVP 阶段用一个最简单的"当前身份"选择器（下拉切换角色，不做真实账号密码），把角色权限的前端隐藏/后端校验逻辑跑通，真实登录系统留到正式上线前再补
2. **存储**：PRD 没有指定数据库——MVP 用 SQLite（单文件、零运维，跟"封闭域、自托管"的产品定位一致），表结构直接对应 Schema v2 的 JSON 结构（整条记录存 JSON 字段，另建索引字段供列表查询，第 33 节"关系表 vs JSONB"思路的 SQLite 版）
3. **7B 引导模型（L 类）**：这个环境没有本地 7B 推理服务可接，也没有外部 API Key——先实现一个**规则驱动的 Mock Guide Service**，接口签名和真实 LLM 版完全一致（第 14 节每轮 LLM 输入/输出协议），先把"专家打字 → 结构化抽取 → DAG 更新"这条主链路跑通、可演示、可测试；真正接 7B 模型时只需要替换这一个模块的实现，不影响其余代码，替换点在第 17.2 节设置页的"专家采集会话引导"这一项
4. **移动端语音识别（V 类，第 6.2 节）**：PRD 要求复用 `web-demo` 已验证的 Qwen Realtime 转写链路（`QWEN_API_KEY` + `input_audio_transcription.completed` 事件），但这个沙箱环境既没有 `QWEN_API_KEY`，也没有可达的 dashscope WebSocket 出口——先用浏览器原生 `SpeechRecognition` API 作为**真实可用、无需密钥**的替代实现（不是模拟：识别结果是真实的，只是识别后端不同，且仅 Chrome/Edge 等部分浏览器支持），三按钮/波形 UI 与转写结果回填/直接发送的产品行为按 PRD 4.3.1 完整实现；组件对外接口（`onTranscript`）与真实链路接入后需要的形状一致，替换时只需要改 `VoiceCapsuleInput.tsx` 内部的 `startRecognition`/`stopRecognition`，不影响其余代码

## 2. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python + FastAPI | 与本仓库另一产品线（`web-demo/`，Python/aiohttp）技术栈接近，团队沟通成本低；FastAPI 自带 OpenAPI/请求校验，适合这种字段多的 Graph Ops 协议 |
| 存储 | SQLite | 零运维、单文件，匹配"自托管/封闭域"定位；后续要换 Postgres 时 SQL 层改动小 |
| 前端 | React + Vite | 官方 React Flow（图渲染库）就是给 React 用的，第 6.1 节已定 |
| 图渲染 | React Flow + elkjs | PRD 6.1 节已定，`dag-view-redesign.html` 的配色/形状规范原样迁移成 React Flow 自定义节点样式 |
| 图布局算法 | elkjs（ELK.js 的浏览器/Node 版本） | 同上 |

## 3. 目录结构（新建，独立于 `web-demo/`，两条产品线不共享代码）

```
expert-collection/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── db.py                   # SQLite 连接与初始化
│   │   ├── models.py               # Pydantic 数据模型（对应 Schema v2）
│   │   ├── graph_validator.py      # 第 3.3/3.4/12.2.1 节 Validator 规则
│   │   ├── graph_ops.py            # add_node/update_node/... 第 16 节 Graph Ops 协议
│   │   ├── guide_service.py        # LLM 引导服务抽象层 + Mock 实现（假设 3）
│   │   └── routers/
│   │       ├── expert_workflows.py # 第 6.4 节接口
│   │       └── auth.py             # 假设 1 的最简身份选择器
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── SessionPage.tsx     # 桌面三栏 / 移动两页+抽屉（第 3、4 节）
    │   ├── components/
    │   │   ├── DagView.tsx         # React Flow + elkjs，样式取自第 11.3 节
    │   │   ├── ChatPanel.tsx       # 会话面板，含第 18 节气泡逻辑
    │   │   └── HistoryDrawer.tsx   # 历史流程列表（第 5、移动抽屉）
    │   └── api/client.ts
    └── package.json
```

Dashboard（13）、实验中心（14）、管理页面（16）、系统设置（17）暂时只有 HTML 参考原型，不在 Phase 1 实现范围（见第 4 节阶段划分），先把采集层这条主链路做扎实。

## 4. 阶段划分（对应 PRD 第 9 节里程碑，落到具体交付物）

| 阶段 | 范围 | 交付物 | 状态 |
|---|---|---|---|
| **Phase 1** | 桌面端专家采集主链路：三栏界面、创建/恢复会话、逐轮对话、Mock Guide Service 产出 Graph Ops、Graph Validator、DAG 实时渲染（第 11 节视觉规范）、完成度计算、最终确认提交 | 可运行的 FastAPI + React 应用，本文档随附启动说明 | **已实现** |
| **Phase 2** | 移动浏览器端（第 2、4、5 节）：两页+抽屉、右滑/左滑手势（5.4）、DAG 只读页（结构统计/规则与经验/待确认信息，4.4.2）、语音口述输入 | 桌面/移动共用同一套 React 组件与后端接口 | **本轮实现（假设 4，见下）** |
| **Phase 3** | 数据集发布 + 十维质量评分 + Dashboard（13）核心视图 | 见下方"Phase 3 子范围" | **本轮实现（假设 5，见下）** |
| **Phase 4** | 实验中心（14）核心链路 + 管理页面（16）+ 系统设置（17） | 见下方"Phase 4 子范围" | **本轮实现（假设 6，见下）** |
| **Phase 5** | 第 18 节会话气泡在真实前端里落地（Mock Guide Service 需要按 18.2 节表格标注每轮问题是否携带气泡选项） | — | 本轮 Phase 1 一并实现（气泡逻辑不复杂，跟主链路强相关，不单独拆阶段） |
| **Phase 6** | 补齐 Phase 2-4 记录的已知缺口：公共集导入+预检+近重复检测（12.2）、导出+匿名化（12.3/12.4）、Dashboard 详情下钻+趋势 Tab（13.4/13.5） | 见下方"Phase 6 子范围" | **本轮实现（假设 7，见下）** |

## 5. Phase 1 完成标准（对照 PRD 验收条款）

- [ ] 新建流程 → 输入文字 → 收到助手回复 + 右栏 DAG 实时更新（第 3.2、6 节流程）
- [ ] Graph Validator 阻断非法结构（孤立节点、decision 少于 2 出口等，第 3.3/3.4 节规则全部实现）
- [ ] 返工语义走 `retry_semantics`，不产生环边（第 7.1 节裁定）
- [ ] 完成度 Completion Score 按第 3.5 节公式计算并展示
- [ ] 结构判断类问题（分支/并行/汇合）带气泡，回忆类问题不带（第 18 节），气泡点击后填入输入框、需手动发送
- [ ] 历史流程列表可以看到并恢复未完成的会话
- [ ] 最终确认页可以提交，提交后生成 `expert_confirmed` 记录
- [ ] DAG 视觉效果对照 `design/dag-view-redesign.html` 的配色/形状规范

不在 Phase 1 范围、Phase 1 不需要做到但不算缺陷：语音输入、移动端、数据集/Dashboard/实验中心/管理页/设置页的真实实现（这些页面目前只有交互原型，属于后续阶段）、真实 LLM 接入（Mock Guide Service 替代）。

## 6. Phase 3 子范围（第 12/13 节完整范围很大，本轮先做能撑起"发布→评分→看板"这条主链路的部分，其余按子项列出留给下一轮）

**本轮实现**：
- 数据集发布（12.0 第 2 点）：管理员触发，把 `expert_collected` 来源里所有 `expert_confirmed` 且尚未进入任何版本的会话打包成一个新的 `dataset_version` 快照，快照不可变
- Dataset Readiness Score v2 十维评分（13.3）：全部按 13.6 节"确定性统计"实现，不用 LLM；发布时批量计算并随版本存下来
- 13.3.1 的"评分标准"静态文案 + "当前分数依据"文字说明：静态文案是固定文本；"当前分数依据"这段按 13.6 节末尾例外条款需要 LLM 才能读起来自然——这个环境同 Phase 1 一样没有可用的 7B/外部模型，先用一个**确定性的模板生成器**（把统计结果、命中样本代入固定句式）产出结构相同、语气稍生硬的说明文字，接口签名对齐"输入统计结果→输出一段话"，方便以后换成真实模型调用，不改动调用方
- Dashboard（13.1.1/13.2/13.3/13.3.1/13.5.1）：一级指标卡片（含 tips）、质量评分 Tab（十维横向条形图 + 状态色 + 解释弹窗）、小样本阈值规则（低于 20 条已确认记录时对应维度显示"样本量不足，暂不评分"）

**本轮不做，记录为已知缺口（不是本轮验收范围内的缺陷）**：
- 12.2 公共集导入（JSON 上传、预检报告、近重复检测）：规则本身不需要 LLM，但预检管线（Schema 校验、TF-IDF/MinHash 文本近重复、Graph Edit Distance 结构近重复）工作量独立于 Dashboard，留到下一轮
- 12.3/12.4 导出与匿名化：匿名化里的人名脱敏明确需要 LLM（12.4），且导出格式/角色归一化本身也是独立工作量，留到下一轮
- 13.1 "专家集/公共集"两类切换：当前只有专家采集一条数据源在跑，公共集导入没做之前这个切换控件没有第二类数据可切，先只做专家集视图，控件本身按设计放上但公共集侧显示"暂无数据"
- 13.4 详情下钻定位问题样本、13.5 趋势 Tab（随时间的走势线）：留到下一轮，跟导入/更多批次数据一起做更有意义（现在只有一次发布，没有"趋势"可言）
- 13.3 里"微工作流识别数"这类需要结构化子图挖掘算法的指标：算法本身不需要 LLM，但挖掘逻辑独立于本轮范围，先占位显示（一级指标卡片里的"微工作流识别数"本轮先诚实显示为待实现，不编造数字）

**假设 5（新增）**：数据集发布目前没有真实的"管理员"登录态（延续假设 1），Dashboard/发布入口先直接暴露在同一个前端里，不做权限门禁——真实权限校验留到接入假设 1 的真实登录系统时一并做。

## 7. Phase 4 子范围（第 14/16/17 节完整范围很大，本轮结构性问题需要先说清楚再动手）

**先说清楚一个结构性落差**：PRD 第 14 节"实验中心"的设计前提是"有一条从原始文本/记录抽取出 Graph 的独立流水线，实验在测这条流水线抽得准不准"，需要与"输入"分离的 **Gold 标注**作为标准答案。但本产品当前的架构是专家直接通过结构化对话产出 Graph（Graph 本身就是"结果"，不是"从别处抽取出来、再拿去和标准答案比对"的东西），而且 Phase 3 已经如实标注标注体系（Gold Annotation）尚未实现。这意味着 PRD 14.3 里依赖 Gold 标注的指标（Branch Condition Accuracy、Role Assignment Accuracy 等）目前没有真实标准答案可比，本轮不编造这些数字。

**本轮实现的替代方案（忠于"方法/模型"这套配置框架，但只让能诚实算出结果的部分真正跑起来）**：
- 实验创建/列表（14.1/14.1.1/14.2）全部字段都做（数据源/数据集版本/Split/表示方式/方法/模型/Prompt/Seed/Gold 勾选……），但**只有 `consensus_dfg`（纯规则图挖掘 baseline，不用 LLM）这一个"方法"真正执行**：把数据集版本按 Seed 切 Train/Test，从 Train 里统计出各节点类型/边类型的"共识结构"，拿 Test 集的图逐条比对，算出真正可计算、不需要 Gold 标注的结构级指标（节点类型分布 F1、边类型分布 F1、结构类型匹配率，对应第 14.3 节 Graph-level 指标里不依赖 Gold 的那部分）。其余方法（`pm4py_inductive`/`pm4py_heuristics`、基于 LLM 的抽取器）在下拉里可选、可创建实验，但点击"Run"后诚实提示"该方法本轮未接入真实执行引擎"，不产出假指标
- 异步执行模型（14.2）：真正的后台任务（FastAPI `BackgroundTasks`），状态 排队中→运行中→已完成/失败 是真实流转，前端轮询，不是假进度条
- 结果页四层结构（14.4）：Summary（真实指标 + 14.5 结果解读卡片）、Graph（复用已有 `DagView` 组件展示挖出来的共识结构图）、Error Analysis（真实：列出比对不上的 Test 记录，按"哪种结构类型不匹配"分组，不用 LLM 二次归纳——14.5.3 的 LLM 归纳步骤留到下一轮）做；**Dataset Slice 本轮不做**（需要行业/制造模式/场景这类本系统未采集的分类字段，跟 Dashboard 覆盖度维度是同一个缺口）
- 14.5 结果解读 / 14.6 对比解读：延续 Phase 3 `explain.py` 的 Mock Explanation Generator 模式，同样的"统计输入→模板生成一段话"调用签名，同样固定加上"以上解读由 AI 自动生成"的免责说明（PRD 14.5.2 的强制要求）
- 实验对比（14.6）：选 2～5 个已完成实验，真实的指标对比表 + 条形图 + 对比解读

**管理页面（16）本轮实现**：
- **真正落地假设 1 的角色选择器**：一个最简单的"当前身份"切换（专家/研究员/管理员，存 `localStorage`），首次把 PRD 16.2 的权限表接到前端——专家身份看不到 Dashboard/实验中心/管理页面的导航入口（此前 Phase 3 加的 Dashboard 导航对所有身份都可见，本轮修正）
- 数据集发布/归档：草稿池发布沿用 Phase 3 已有接口；新增"归档"（软删除，保留数据不物理删除）
- 审计日志：如实缩小范围——当前没有真实多用户登录，"谁"只能记到当前选择的身份，不是真实账号；只记录**数据集发布**这一类真正在发生、有意义的操作（谁/什么时候/发布了哪个版本），节点/边级别的修改审计需要更细的变更溯源存储，留到下一轮
- 用户与权限管理（账号列表）：不做——没有真实账号体系（假设 1），做一个假的账号列表页没有意义，留到接入真实登录系统时一起做

**系统设置（17）本轮实现**：
- 17.2/17.3 LLM/语音模型配置：真实的表单 + 后端持久化（服务地址/模型名/温度等），**"测试连接"按钮如实反馈**——当前没有可达的真实推理服务，点击后诚实提示"未配置可达的推理服务，无法测试连接"，不伪造"连接成功"
- 17.4 质量评分与检测参数：真实生效，不是摆设——"小样本评分阈值"这一项直接接到 Phase 3 `quality.py` 的 `MIN_SAMPLE_SIZE`，改了设置页的值下一次发布真的会用新阈值计算
- 17.5 其他运行参数：并发实验数上限、单次 Run 超时时间接到本轮新增的实验执行器上，真实生效

**假设 6（新增）**：LLM 配置项在设置页保存后，由于本轮没有真实可达的 L/C 类推理服务，配置不会真正切换任何环节的行为（Mock Guide Service / Mock Explanation Generator 继续工作）——设置页本身是真实的、可用的配置管理界面，只是下游"生效"这一环还没有真实模型可接，跟 Phase 1 假设 3、Phase 2 假设 4 是同一类"接口对齐、实现留空"的诚实占位。

## 8. Phase 6 子范围：补齐 Phase 2-4 记录的已知缺口

按用户选择"补齐已记录的缺口"，本轮处理第 12/13 节里 Phase 3 标记为"留到下一轮"的三块。第 14 节 Dataset Slice（需要行业/制造模式/场景分类字段）和 14.5.3 的 LLM 案例聚类仍然留到之后——本轮先把数据源和 Dashboard 这条线做完整，实验中心的下钻留在有更多批次实验数据后再做更有意义。

**12.2 公共集导入 + 预检 + 近重复检测（本轮实现）**：
- 导入格式直接采用 `schema/workflow_graph_schema_v2.json` 定义的 `{dataset_meta, records[]}` 结构——这就是 PRD 12.2.1 说的"上传 JSON"的具体格式，不用另外发明一套
- 预检流程按 12.2.1 的十步清单实现：JSON Schema 校验（用 `jsonschema` 库对照 v2 schema）、`source_type` 一致性、必填字段完整度、`manufacturing_mode`/`workflow_type` 枚举值校验、Graph Validator（复用 Phase 1 的 `graph_validator.py`，跟专家采集同一套规则）、`record_id` 重复检查、近重复检测、角色完整度、Gold 标注可用性检查（如实：本系统还没有标注体系，这一项固定报告"不可用"）、自动生成预览评分（复用 Phase 3 `quality.py`）
- 近重复检测（12.2.2）**真实实现，规则/统计方法**：文本层用 trigger 文本 + 节点标签的词级 Jaccard 相似度（PRD 建议 TF-IDF/MinHash，这里选精确 Jaccard——同样是无监督统计方法，规模小时比近似算法更准确、不引入近似误差，达到同样的"不用 LLM"目的）；结构层用节点类型集合 Jaccard + 边类型集合 Jaccard 的均值，作为 Graph Edit Distance 的**近似代理**（如实标注：不是精确 GED，精确 GED 计算量大，在预检这种要给出即时反馈的场景不合适）。两个阈值都接到 Settings 17.4 的 `near_dup_text_threshold`/`near_dup_structure_threshold`
- 预检只出报告，不入库；"确认导入"即发布（12.0 第 3 点）——直接为 `public_extracted` 创建一个新的 `dataset_version`，不像专家采集那样先进草稿池

**12.3/12.4 导出与匿名化（本轮实现）**：
- 导出范围：整个数据集版本 / 按 `source_type`、`workflow_type`、`graph_type` 筛选
- 三种格式：`raw`（原样）、`role_normalized`（规则+同义词典映射角色名到标准角色，不需要 LLM，本轮实现）、`anonymized`（在 `role_normalized` 基础上做 12.4 的脱敏规则）
- `anonymized` 规则式部分本轮真实实现：`expert_id_hash` 保留哈希、经验年限分桶（如"30年以上"）；**人名脱敏**按 PRD 12.4/15.2 的说法明确需要 LLM 才能达到可用召回率——本轮延续 Mock 模式，用一个姓氏词典 + 常见"XX工/XX师/XX主管"称呼模式的正则规则兜底（PRD 原文说的"规则兜底"部分），如实标注这是规则兜底、不是真正的 LLM 语义识别，召回率有限，接口留好后续换成真实模型调用的位置
- 导出文件保留 `dataset_meta.source_type` 和每条记录 `provenance.source_type`（PRD 12.3 强制要求）

**13.4/13.5 Dashboard 详情下钻 + 趋势 Tab（本轮实现）**：
- 13.4 点击任意维度分数 → 展开该维度的子指标明细；"定位问题样本"按维度找出拖分的具体记录（例如孤立节点比例低分 → 列出所有含孤立节点的记录）——这是真实可算的，不需要额外基础设施
- 13.5 趋势 Tab：随着本轮导入功能上线、可以产生多个 `dataset_version`，趋势折线图（Readiness Score 及各维度分数随发布批次的走势）现在有真实数据可画，不再是 Phase 3 时"只发布过一次、没有趋势可言"的状态

**本轮仍不做，继续记录为已知缺口**：
- 14.4 Dataset Slice、14.5.3 Error Analysis 的 LLM 二次归纳：留到实验数据积累更多批次后
- 13.1 专家集/公共集两栏对比统计（本轮只是让公共集有真实数据可看，两类并排对比的趋势图留到之后）
- 真实 LLM 接入（人名脱敏、Guide Service 等）：跟 Phase 1-4 一样，等有可达的 L/C 推理服务再替换对应 Mock 模块，接口已经按"这次调用要接收什么、返回什么"设计好

**假设 7（新增）**：近重复检测的两个阈值本轮从 Settings 读取，但公共集导入界面本身没有做管理员权限门禁（延续假设 5 的"暴露在前端里、权限校验留到真实登录系统接入时一并做"）。

## 9. Phase 7：Scenario/Case Context 采集 + Prior 标注流程

对应 `docs/expert-workflow-collection/design/case_context_and_prior_annotation_draft.md` 定稿后的两处扩展。文末"决策记录"表的 4 个决定在本轮直接实现，不再重复推导；这里只记录落成代码时的具体取舍。按草稿建议的顺序拆成两个独立子阶段，分别提交：

### 9.1 子阶段 A — Scenario / Case Context 采集（改动面小，先做）

- `guide_service.py`：在现有 `opening → trigger_detail` 之间插入 7 个新 stage：`scenario_trigger` / `scenario_goal` / `scenario_success`（A组，直接复用现有"chip 只回填输入框"机制——两个 chip 文案本身就是"简单说：" / "详细说：提示语——"的答案模板前缀，专家在其后接自己的话；guide_service 靠前缀识别 `detail_level`，不需要新的前端交互）；`context_known` / `context_unknown` / `context_constraints` / `context_resources`（B组，每个问题拆成"选择"+"澄清"两个 stage，选择 stage 用多选 chip、命中非"无"的 chip 才进入澄清 stage，"无"直接跳到下一题）。C组的"为什么这样做"归因追问（PRD 里原设计的一部分）本轮**不做**，作为已知缺口记录在 9.3——它要求把现有 `main_path`/`branch_check` 等每个 stage 都拆成两段，改动面明显大于 A/B 两组，留到下一轮单独评估。
- `models.py`：新增 `CaseContext` 模型（`scenario_trigger/goal/success`、`known_info`/`unknown_info`/`constraints`/`available_resources`、`detail_level: dict`、`skipped_fields: list`），`WorkflowRecord` 新增 `case_context: Optional[CaseContext]`。
- `NextQuestion` 新增 `chip_mode: Optional[Literal["prefill", "multi_select"]]`，默认 `None`（等价于现有行为，所有旧 stage 不用改）；B组四个 stage 的选择环节设为 `"multi_select"`。
- `routers/expert_workflows.py`：`post_turn` 里把 `new_state["pending"].get("case_context")` 同步写回 `record["case_context"]`；`end_condition` stage 把 pending 清空成 `{}` 时要保留 `case_context`（原代码会连带清掉，是一个真实需要修的点，不是新增行为）。
- 前端 `ChatPanel.tsx`：新增 `chip_mode === "multi_select"` 的渲染分支——chip 变成可切换选中状态的按钮组 + 一个"确认选择"按钮，点击后把选中项拼成字符串回填草稿框（沿用"永不自动发送"的规则，不新增例外）；`chip_mode` 为空或 `"prefill"` 时行为完全不变。
- 前端 `SessionPage.tsx`：`active.graph.nodes.length === 0` 时右栏显示"背景信息收集中"占位态而不是空 DAG——这个条件本身就和"A/B 组阶段"重合，不需要额外按 stage 名判断。
- `quality.py`：不改动评分公式本身（草稿 1.7 已经说这是要不要计入总分的产品决策，本轮不擅自决定），只在 `completeness` 维度的 `sub_indicators` 里新增一个诊断字段 `case_context_fill_rate`（七个字段里非跳过的比例，跨数据集版本的平均值），先展示不影响分数。

### 9.2 子阶段 B — Prior 标注（链式单人标注，改动面大，后做）

- `models.py`：新增 `prior_status: Literal["raw", "expert_annotated"]`（只在 API 响应里按 9.2 的方式动态算出，不写回不可变的 `dataset_version` 数据）、`PriorVerdict = Literal["accepted", "needs_revision", "rejected"]`、`CreateAnnotationRequest`、`PriorAnnotation`（含 `based_on_annotation_id`，草稿 2.4 的链式设计）、`PriorRecordSummary`、`AnnotationSummary`。
- `db.py`：新增 `prior_annotations` 表，`id/version_id/record_id/based_on_annotation_id/data/annotated_at`；`save_annotation`/`list_annotations(version_id, record_id)`/`latest_annotation(version_id, record_id)`/`list_annotations_for_version(version_id)`。标注按 `(version_id, record_id)` 定位，不去改 `dataset_versions` 表里已发布版本的不可变数据——这样"标注"和"版本不可变"两条规则不冲突。
- 新增 `routers/annotations.py`：
  - `GET /api/datasets/versions/{version_id}/records`：列出该版本所有记录 + 动态算出的 `prior_status`/`latest_verdict`/`node_count`，供标注列表用
  - `GET /api/datasets/versions/{version_id}/records/{record_id}`：单条记录详情（图 + 标注历史链），标注面板预填链上最新判定用
  - `POST /api/datasets/versions/{version_id}/records/{record_id}/annotations`：提交新标注，`based_on_annotation_id` 自动指向该 (version_id, record_id) 当前链上最新一条
  - `GET /api/datasets/versions/{version_id}/annotation-summary`：标注覆盖率 + 判定分布，供 Dashboard 用
- 只对 `source_type == "public_extracted"` 的版本开放（草稿 2.1：LLM 整合工作流本轮只走导入，和其他导入数据用同一套，不需要区分）；对 `expert_collected` 版本调用这组接口直接 404，不悄悄放行。
- 前端新增 `PriorAnnotationPanel.tsx`：复用只读 `DagView`，三个大按钮（采纳/需要修改/丢弃）默认预选链上最新判定；选"需要修改"才展开逐节点 `保留/删除/合并进上一个节点` chip。
- `DashboardPage.tsx` 公共集分支：记录列表旁加状态标签 + "去标注"按钮，新增"标注覆盖率"统计卡片，读取 `annotation-summary`。
- `client.ts`/`types.ts`：新增对应的请求函数和类型。

### 9.3 本轮仍不做，继续记录为已知缺口

- C组"为什么这样做"的节点级归因追问（见 9.1）：需要把现有主流程每个 stage 拆成两段，工作量和现有 FSM 的 stage 总数成正比，留到下一轮单独排期。
- B组 `context_known`/`context_unknown`/`context_resources` 三个问题的具体 chip 文案（草稿"下一步细化项"提到需要贴合真实业务场景再定）：本轮先用草稿里给的合理默认值实现机制，文案后续可直接改 `guide_service.py` 里的常量表，不涉及结构改动。
- 标注一致性（Cohen's κ / Krippendorff's α）：按决策 3，本轮不做，`based_on_annotation_id` 的链式设计已经为以后升级成多人独立标注留了口子（草稿 2.4 结尾）。
- `case_context_fill_rate` 是否要真正计入 Dataset Readiness Score 总分：本轮只展示不计分，计不计分是产品决策，留给下一轮。

## 10. 跨版本近重复检测（严格把关，已实现）

在实际导入两批公共集数据时发现并当场修复的产品缺口，不是本轮 Phase 7 设计里预见到的，单独记一节。原先只是记为已知缺口，后来按用户明确要求（"每次导入新数据的时候，都要做好严格把关"）当场实现，本节记录最终实现和过程中的一次真实调参。

**发现过程**：导入第一批 20 条公共集（`manufacturing_workflows_consolidated_v2.json`）生成 v1 之后，再导入第二批 40 条，系统的预检报告对这两批之间的重复完全没有反应——因为 `import_pipeline.precheck` 的近重复检测（12.2.2）原来只在**当前这一次上传的 payload 内部**两两比较，从来不和数据库里已经导入过的历史 `dataset_version` 比。手工用 `import_pipeline._jaccard`/`_record_structure_sets` 把两批原始记录做了一次跨批比较，找到 78 组结构近重复，预检报告里一条都没出现，证实这是真问题。

**实现**（`import_pipeline.py` + `routers/datasets.py`）：
- `precheck()` 新增 `existing_records` 参数：调用方（`routers/datasets.py`）负责从数据库取出**同一 `source_type` 下所有未归档版本**的记录（复用现成的 `_records_for_export`），`import_pipeline.py` 本身不碰数据库，保持纯函数、方便单测
- `record_id` 唯一性检查（原第 6 步）从"只查本批"扩展为"本批 + 历史"：任何 record_id 已经出现在历史已发布版本里，直接算错误（`record_id_already_exists`），阻断该条导入
- 新增独立的**查重接口** `POST /api/datasets/duplicate-check`：不依赖导入流程，单独传 `{dataset_meta, records[]}` 就能拿到分类结果，用来在决定要不要修数据、要不要导入之前先看一眼这批数据和已有数据的关系；内部复用和 `precheck` 完全同一套分类逻辑（`import_pipeline.compare_cross_version`），保证这里看到的结果和真正导入时会被拦下的结果一致，不是另一套口径

**分类逻辑——两级判定，按场景是否重复 + 结构是否重复两个维度分开定义（这是根据反馈明确要求的判定方式，不是延续上一版"文本命中就阻断、结构命中就警告"的裁剪版本）**：
- **整体重复**（`duplicate`）：文本相似度**和**结构相似度**同时**达到阈值——做的事情（场景）重复，做的工作流（结构）也重复，判定为真正的重复数据，默认阻断导入
- **疑似微工作流复用**（`microflow_reuse_candidate`）：文本相似度**没**达到阈值，但结构相似度达到阈值——做的事情不一样，中间的处理结构却很像，判定为疑似复用了同一个可复用的 micro-workflow 模板（呼应实验设计文档 §4.4："同一个 micro-workflow 故意在多个场景里重复出现"），只警告、不阻断，交给 Prior 标注环节人工复核
- 极少数"文本相似但结构不同"的组合单独归为 `content_match_structure_diff`，同样只警告，不强并入前两类

这个两级判定同时应用在批内比较（`_find_near_duplicates`）和跨版本比较（`_find_cross_version_duplicates`）上，口径统一——批内如果真的整体重复（同一批文件里不小心塞了两条一样的数据）也会被阻断，不再像之前那样"批内一律只警告"。

**已验证（在干净的 v1 基线上重新走了一遍完整闭环，不是接着之前测试残留的脏状态继续测）**：
1. 清空测试库，只留最初那 20 条真实数据作为 v1
2. 对修好的 40 条数据调用 `/duplicate-check`：`duplicates: 0`、`reuse_candidates: 348`、`other_matches: 0`——因为这 40 条从未导入过，和 v1 的重叠纯粹是结构模板共享，符合预期
3. 走完整 `precheck`：40/40 可导入，0 个阻断错误，1052 条警告全部是 `microflow_reuse_candidate`（704 批内 + 348 跨版本）
4. 确认导入为 v2，40 条全部成功
5. 对完全相同的文件再跑一次 `/duplicate-check`：这次正确识别出 **40 个 `duplicate`**（文本相似度 1.0 且结构相似度 1.0 的自我匹配），证明真正的重复不会被放过

**仍未做（下一轮）**：
- 跨批结构命中要不要在 Prior 标注环节里显式呈现"这条和历史某条结构相似"供专家参考，目前只是预检报告里的一条警告文字，标注面板本身还没读取这个信号
- 计算量会随历史数据量增长而变大（每次导入都要和全部历史记录比较一遍），目前 40 vs 20+8+32 的规模完全没问题，等数据量大到有性能问题时再考虑索引/分桶优化，现在不提前做

## 11. 模型配置改为"级别优先"，环节只引用级别

按反馈修的产品缺陷："现在的模式重复配置没必要"——原来 `Settings.llm_configs` 是 8 个环节（专家采集会话引导/移动端语音口述整理/……）各自一份完整配置（`category` + `endpoint` + `model_name` + `temperature` + `api_key`），即使多个环节实际用的是同一个模型级别（比如都是 `C_standard`），端点/模型名/API Key 也要在每个环节的表单里分别填一遍、改的时候要记得同步改好几处。

**改法**：拆成两层。
- `llm_levels`（新增，3 个级别：`L`/`C_standard`/`C_flagship`，每个只配一次）：`endpoint`/`model_name`/`api_key`——这才是真正意义上"重复"的部分，同一个级别只有一份连接信息
- `llm_slots`（原 `llm_configs` 改名）：每个环节只保留 `level`（引用哪个级别）+ `enabled` + `temperature`——`temperature` 特意留在环节这一层没有并进级别，因为同一个级别下不同任务想要不同的采样温度是合理的调优需求（比如 `guide_service` 用 0.1、`mobile_speech_polish` 用 0.2，都是 `L` 级别），这不是"重复配置"，是任务级别的真实差异，不能一并砍掉

新增 `settings.resolve_slot(settings, slot)` 帮助函数：把某个环节引用的级别信息和它自己的 `enabled`/`temperature` 合并成一份完整视图，真正要调用模型的代码只需要调这一个函数，不用自己去做级别查找和合并。

`POST /api/settings/llm/{slot}/test-connection` 改成 `POST /api/settings/llm-levels/{level}/test-connection`——测试连接本来就是在测"这个连接通不通"，既然多个环节共享同一个级别的连接，按环节测是没有意义的重复测试，按级别测一次就够了。

**已验证**：真实 HTTP 调用——只给 `C_standard` 级别填一次连接信息，把 `error_clustering` 和 `dashboard_explain` 两个环节都指向它，两个环节各自读到的仍然是它们自己的 `enabled`/`temperature`，但连接信息（`endpoint`/`model_name`/`api_key_set`）自动一致，不需要分别填两遍；`resolve_slot()` 正确合并出两个环节各自完整的等效视图；给一个环节传不存在的 `level` 值会被 400 拒绝；`tsc -b` 通过；headless Chromium 截图确认页面正确分成"模型级别配置"（3 张卡片）和"环节引用级别"（8 行，每行只有级别下拉 + temperature + 启用勾选 + 保存，不再有端点/模型名/Key 输入框）两个区块。

## 12. 节点拆分：一句话里的复合动作不再塞进一个节点

真实截图暴露的问题："是质检员发现的，第一时间就记录系统并通知对应的车间班组长" 这一整句话被原样塞进了一个 `activity` 节点，实际上是两件事（记录系统 / 通知班组长），外加一段跟步骤本身无关的"谁发现的"背景交代。反馈明确要求：不能是把专家原句原样搬进框里——不管最后拆成一步还是两步，框里放的都必须是"对这一步的描述"，而不是从原文里抠出来的一句话。

这跟 `guide_service.py` 文件头一直强调的"Honest Mock：内容完全按专家原话逐字记录，不做任何 NLU"的设计原则是有真实张力的——诚实地说，这个 Mock 没有真正的语义理解/摘要能力，不可能做到"提炼出专家没有明确说出的表述"那种意义上的抽取。能在不越界（不产生专家没说过的内容）的前提下做到的，是**机械规则**，不是语义抽取：

- 去掉开头一段"谁发现的/怎么知道的"背景交代（`是XX发现的，`/`XX反馈的，` 这类固定模式）——这部分内容本来就该属于已经单独问过的 `scenario_trigger`/case context，不是这一步动作本身。
- 按一个固定的、封闭的并列连接词集合（`并`/`同时`/`然后`/`、`，跟 PRD 18 节里已经在用的"chip 是封闭选项集合，直接模式匹配没问题"是同一个思路，不是通用分句）切成最多两段。
- 去掉切出来的每一段开头的时序填充词（`第一时间就`/`随后`/`先`/`再` 等），让节点标签读起来像"记录系统"这样的动作描述，而不是"第一时间就记录系统"这样的原句片段。

**没有做**、也做不到的：真正意义上的提炼/改写/摘要（比如把"叫维修工老王来拆开看看是不是传感器坏了"提炼成"排查传感器故障"这种需要理解语义才能生成的表述）——这仍然超出 Honest Mock 的能力边界，留给真正接入 L 模型之后（PRD 15.0/17.2）。

**实现**：`guide_service.py` 新增 `_extract_step_clauses(text, max_steps=2)`（做上面三步机械处理，返回 1-2 段文本）和 `_add_step_nodes(ops, from_id, text, ...)`（按提取结果链式创建 1-2 个 `activity` 节点，返回新的 cursor），替换了 `trigger_detail`/`main_path`/`branch_condition_a`/`branch_condition_b`/`parallel_branch_a`/`parallel_branch_b` 六处原来"整句 `text[:40]` 塞进一个节点"的写法。

**已验证**：真实 HTTP 端到端跑通完整对话流程（含 Scenario/Case Context 采集），把截图里的原句 "是质检员发现的，第一时间就记录系统并通知对应的车间班组长" 发给 `trigger_detail` 阶段，返回的图正确生成了「开始」→「记录系统」→「通知对应的车间班组长」三个节点、两条 `normal` 边，"是质检员发现的" 背景交代被正确去掉；单句无连接词的输入（如"维修工到场维修"）保持原样单节点不受影响；`main_path` 阶段同样验证了三段式压缩为两段（"记录、通知、并归档" → "记录" / "通知、归档"）。

## 13. 复合句"并/同时"的串并行歧义：改成追问，不再默认串行；"更正语句"识别记为已知缺口

真实线上截图（`workflow-data.inkpath.cc`）复测第12节的修复时又暴露两个问题，都是"规则匹配没有语义理解"这条 Honest Mock 边界带来的真实代价：

**问题 A：专家说"我说错了，……"这种更正/撤回语句，被当成普通的下一步塞进图里。** 例如专家在 `main_path` 阶段回复"哦，我说错了，做这两步之前我会先做复检。确认后才会记录系统和通知班组长"，系统没有能力识别"这是在更正上一句"还是"这是新的一步"——`guide_service.py` 文件头本来就写明"它永远机械地把新一轮输入当成往前推进一步"，这次是这条设计边界第一次被真实数据踩到。

真要解决这个问题，需要两件事：(1) 判断一句话是不是在更正前面的内容——这是纯语义判断，封闭关键词表（"我说错了"/"不对"/"应该是"……）必然会漏判（更正语句的说法太多样）或者误判（"不对"完全可能出现在正常业务描述里），跟第12节里"chip 是封闭选项集合，模式匹配没问题"不是一回事；(2) 就算识别出来了，"撤销上一步"这个操作本身现在也不存在——`graph_ops.py` 只有 `add_node`/`add_edge`/`update_node` 这类前进操作，没有"撤销/回退到某个节点"的能力，而且"撤销几步"这个范围本身也是要靠语义理解才能判断的（这次的例子里，专家说错的到底是最近1个节点还是2个节点，从文字本身并不是完全无歧义的）。

**决定（用户明确选择）**：这两件事现在都不做，留作已知缺口，等真正接入 PRD 15.0/17.2 的 L 模型后再解决——现在这个阶段不用规则硬凑一个不可靠的模拟。产品影响：专家发现自己说错话之后，仍然需要自己在图上手动删除/修改错误节点，系统不会自动帮忙撤销。

**问题 B：复合句里的"并"默认当串行处理，没有跟专家确认过。** 第12节的 `_extract_step_clauses` 按 `并`/`同时`/`然后`/`、` 这组封闭连接词切句子，但不管碰到哪个连接词，`_add_step_nodes` 一律用 `normal`（串行）边把切出来的两个节点连起来。这本身不够诚实：`然后`/`、` 读起来确实没有歧义（先后关系很明确），但"记录系统**并**通知班组长"里的"并"，语义上完全可能是"同时做"而不是"先后做"——系统里本来就有专门的 `先后做`/`同时做` chip 用来问这个问题（`parallel_check` 阶段），但那一套之前只在专家**换行**另起一步时才会触发，句子内部切出来的分句从来没有走过这个确认流程。

**决定（用户明确选择）**：遇到"并/并且/同时"作为切分连接词时，追加一次澄清提问，复用现成的 `先后做`/`同时做` chips，由系统据此生成对应结构，而不是先猜后问。"然后"/"、" 语义上已经足够明确是先后关系，不需要额外确认。

**实现**：`guide_service.py` 新增：
- `_needs_parallel_clarify(text)`：只有当 `_extract_step_clauses` 切出恰好两段、且实际生效的切分连接词是"并/并且/同时"时才返回 `True`（`然后`/`、` 切分不触发）。
- `_build_step_chain` / `_build_parallel_branches`：把原来 `_add_step_nodes` 里"建节点"的部分拆成两种可复用的建图方式——前者按顺序链式建 `activity` 节点（原来的行为），后者建一个完整的 `parallel_split → 各分句一个 activity（parallel 边）→ parallel_join` 结构。
- `_continue_after_step(resume, tail_id, pending, ops, entry_id=None)`：把"这一步节点建完之后要问什么、进入哪个 stage"这部分逻辑，从原来 6 个 stage handler 里各自内联的代码，收敛成一个共享函数——不管是直接建图（无歧义）还是等专家答完"先后做/同时做"之后再建图（有歧义），走的都是同一段"之后怎么问"代码，不会出现两条路径各写一遍、后续改一处忘了改另一处的问题。
- `_start_parallel_clarify` / `_resolve_parallel_clarify`：新增一个 `compound_parallel_clarify` stage，把分句结果暂存在 `pending._compound` 里，问完 chip 之后专家的下一轮回答（"先后做"/"同时做"/"不确定，再想想"）不会被当成新的步骤内容去重新提取，而是只用来决定走哪种建图方式；"不确定，再想想" 和其它非"同时"的回答一样，诚实地退回串行（跟 `parallel_check` 阶段现有的三态 chip 处理方式一致）。
- 六个原来直接调用 `_add_step_nodes` 的入口（`trigger_detail`/`main_path`/`branch_condition_a`/`branch_condition_b`/`parallel_branch_a`/`parallel_branch_b`）全部先判断 `_needs_parallel_clarify`，命中就转去问 chip，不命中才维持原来的直接建图行为。

**踩过的坑**：第一版实现里，`trigger_detail` 阶段先把"开始"节点的 `add_node`/`set_start` 操作塞进 `ops` 列表，再判断要不要转入澄清分支——但转入澄清分支的函数当时返回的是一个全新的空列表，把已经排队的"开始"节点操作整个丢掉了，导致专家选完"同时做"之后，图上有并行结构但没有"开始"节点、`start_node_ids` 是空的。用真实 HTTP 全流程测试才测出来（直接看 `_needs_parallel_clarify` 单测是看不出这个问题的，因为它不牵扯 `ops` 列表）。修复：让 `_start_parallel_clarify` 接收调用方已经排好的 `ops` 并原样带出去，而不是自己另起一个空列表。

**已验证**：真实 HTTP 端到端跑通，覆盖了 `trigger_detail`（含上面那个"开始"节点丢失的回归测试）、`main_path`、`branch_condition_a`（确认 `entry_id` 机制正确让 `branch_condition_b` 还能从同一个判断节点继续问"另一种情况呢"）、嵌套的 `parallel_branch_a`（一个已经在并行分支里的步骤，自己又是复合句，需要生成"外层并行 + 内层并行"两层结构）——"先后做"和"同时做"两种回答都验证了对应的图结构（前者是链式 `activity`，后者是 `parallel_split`/`parallel_join` 结构），"然后"/"、" 连接词确认不会触发澄清提问（沿用第12节已验证行为）。
