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
| **Phase 3** | 数据集导入导出（12）+ Dashboard（13）实现 | — | 后续（原型已有） |
| **Phase 4** | 实验中心（14）+ 管理页面（16）+ 系统设置（17，届时把 Mock Guide Service 换成真实 L/C 模型接入点） | — | 后续（原型已有） |
| **Phase 5** | 第 18 节会话气泡在真实前端里落地（Mock Guide Service 需要按 18.2 节表格标注每轮问题是否携带气泡选项） | — | 本轮 Phase 1 一并实现（气泡逻辑不复杂，跟主链路强相关，不单独拆阶段） |

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
