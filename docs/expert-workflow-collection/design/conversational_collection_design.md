# 会话式制造专家 DAG 工作流采集设计
## Conversational Expert Collection — DAG-first v2.1

**适用范围**：制造专家真实流程采集  
**目标用户**：MES、车间管理、质量、设备、工艺、计划、IE、精益生产等制造专家  
**数据输出**：Graph-based Workflow Schema v2 的 DAG 规范子集  
**核心原则**：专家自然表达，系统负责结构化；专家不需要学习 DAG/BPMN/流程建模术语。

---

# 1. 本次升级目标

旧版会话采集仍然隐含“步骤序列”的思路，右侧主要显示已识别步骤。

新版改为：

> **Conversation UI + DAG State + 7B LLM Guide + Graph Ops + DAG Validator + Expert Confirmation**

采集对象不再是：

`step1 → step2 → step3`

而是：

- Node
- Edge
- Branch
- Decision
- Parallel Split
- Parallel Join
- Merge
- Handoff
- Approval
- Start / End
- Rule
- Experience Judgement
- Evidence

---

# 2. 为什么专家采集层采用 DAG

制造现场常见：

- 条件分支
- 多角色并行处理
- 多分支汇合
- 审批
- 交接
- 异常升级

这些都不能用单一线性步骤完整表达。

因此专家采集的**规范主图**采用 DAG（Directed Acyclic Graph）。

优点：

1. 能表达分支、并行和汇合；
2. 可以稳定做拓扑排序；
3. 便于计算 Node / Edge / Branch / Parallel 指标；
4. 便于转换为 Event Log、文本序列、Process Mining 输入；
5. 便于训练和评估 Workflow Extraction。

---

# 3. 如何处理制造流程中的“返工 / 重试 / 回到前面”

真实制造流程可能天然有环，例如：

`试产 → 检验不合格 → 再调整 → 再试产`

如果直接把这个“返回”画成边，主图就不再是 DAG。

本系统采用：

> **DAG 主图 + Rework / Retry 语义引用**

即：

主 DAG 只表示“一次流程实例的逻辑展开”。

返工或重试保存为节点附加语义：

```json
{
  "retry_semantics": {
    "enabled": true,
    "rework_reference_node_id": "n5",
    "condition": "首件检验仍不合格",
    "description": "重新进入原因处理阶段"
  }
}
```

注意：

- `rework_reference_node_id` 不是 DAG Edge；
- 不参与 DAG 拓扑结构；
- 在实验需要有环图时，可以由转换器恢复为 Directed Graph；
- 专家界面用“如果没通过，会重新做哪一段？”来采集，不出现“Loop Back”术语。

这样同时满足：
- 真实业务表达
- DAG 实验稳定性

---

# 4. 页面总体布局

专家采集是默认主页面。

采用固定竖向三栏：

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Logo                         DAG v2             帮助 / 管理员登录       │
├────────────────┬───────────────────────────────┬────────────────────────┤
│ 左栏           │ 主栏                          │ 右栏                   │
│ 历史流程       │ 会话式采集                    │ 当前整理出的 DAG       │
│                │                               │                        │
│ 流程A          │ AI ↔ Expert                   │ Graph                  │
│ 流程B          │                               │ Rule / Experience      │
│ 流程C          │ 自然语言输入                  │ 待确认项               │
│                │                               │                        │
│ + 新建流程     │                               │                        │
└────────────────┴───────────────────────────────┴────────────────────────┘
```

推荐桌面宽度：

- 左栏：240–280 px
- 主栏：自适应，占最大空间
- 右栏：400–460 px

移动端允许三栏纵向堆叠，但桌面端固定三栏。

---

# 5. 左栏：历史流程清单

## 5.1 目标

专家不是一次只提供一个流程。

系统应让专家能够：

- 连续贡献多个流程
- 回到未完成流程
- 修正旧流程
- 补充变体
- 查看已提交结果

## 5.2 每条流程显示

至少：

- 流程名称
- 行业
- 场景
- 状态
- 完成度
- 最近更新时间

示例：

```text
CNC尺寸超差处理
精密机加工 · 质量异常
采集中 · 67%
刚刚
```

## 5.3 状态

- `draft`
- `collecting`
- `needs_confirmation`
- `expert_confirmed`
- `submitted`

## 5.4 左栏操作

支持：

- 新建流程
- 搜索
- 按状态筛选
- 按场景筛选
- 继续会话
- 复制为变体
- 删除草稿
- 查看历史版本

已提交 Workflow 再修改时：

> 创建新版本，不覆盖旧版本。

---

# 6. 主栏：会话式采集

## 6.1 开场

不要先要求专家填：

- 制造模式
- 行业
- 岗位
- 设备
- 系统

优先让专家进入真实记忆：

> “请回忆一件你亲自参与、比较熟悉的制造工作。可以是异常处理、标准生产、持续改善或工程变更。”

必要时提供快捷选择：

- 设备 / 质量异常
- 标准生产工作
- 持续改善
- 工程 / 工艺变更

快捷按钮仅帮助回忆，不强制分类。

---

# 7. 7B LLM 的职责边界

7B 模型只负责：

1. **引导**
2. **复述**
3. **澄清**
4. **结构化抽取**
5. **Graph 结构识别**
6. **选择下一条最有信息价值的问题**

模型不得：

- 猜测未说出的事实
- 自动补 SOP
- 编造角色
- 编造阈值
- 自动增加系统
- 把制造常识当作专家事实
- 为了图完整而创造 Node / Edge
- 静默解决前后冲突

---

# 8. 会话不是固定 Wizard

后台有采集阶段，但专家不看到“第1步、第2步”。

推荐内部阶段：

1. `trigger_discovery`
2. `main_path_discovery`
3. `branch_discovery`
4. `parallel_merge_discovery`
5. `actor_system_discovery`
6. `rule_judgement_discovery`
7. `end_condition_discovery`
8. `expert_review`

阶段不是严格串行。

如果专家提前讲出后面信息，应立即提取。

---

# 9. DAG 追问优先级

## P0：主干完整性

优先确认：

- 什么触发
- 谁先开始
- 第一动作
- 后续动作
- 谁接手
- 正常结束点

## P1：条件分支

寻找：

- 是否存在不同处理结果
- 什么条件决定走哪一条
- 分支是否互斥
- 分支后是否合并

专家问题：

> “这里是不是只有一种处理方式，还是不同情况下会走不同方向？”

> “什么情况下走 A，什么情况下走 B？”

## P2：并行

寻找：

- 两件事是否可以同时执行
- 是“同时做”还是“先后做”
- 是否必须全部完成才能继续

专家问题：

> “设备检查和工艺检查是先后做，还是可以同时进行？”

## P3：汇合

区分：

### Merge
多个互斥分支最终回到同一步。

### Parallel Join
多个并行分支都完成后才进入下一步。

专家问题：

> “这两个处理完成以后，是各自继续，还是结果要汇总后再进入同一步？”

> “必须两边都完成，还是任意一边完成就可以继续？”

## P4：审批 / 交接

寻找：

- 谁把工作交给谁
- 谁最终批准
- 是否存在等待状态

问题：

> “这一步做完后，是直接继续，还是需要某个人确认/批准？”

## P5：返工 / 重试语义

不生成回环 Edge。

问题：

> “如果这次检查仍不合格，会重新做前面的哪一段？”

保存为 `retry_semantics`。

## P6：规则与经验

确认：

- 正式规则
- 现场经验
- 两者差异

## P7：研究增强

例如：

- 新手 / 老手差异
- 白班 / 夜班差异
- 不同产品变体
- 少见异常路径

---

# 10. DAG Node 类型

专家采集 MVP 建议支持：

- `start`
- `activity`
- `decision`
- `parallel_split`
- `parallel_join`
- `merge`
- `approval`
- `handoff`
- `wait`
- `end`

后续可扩展：

- `event`
- `subprocess`

---

# 11. DAG Edge 类型

主 DAG 只允许无环 Edge：

- `normal`
- `conditional`
- `parallel`
- `merge`
- `handoff`
- `approval`
- `timeout`
- `exception_forward`

不允许：

- `loop_back`

返工使用 `retry_semantics`。

---

# 12. 会话状态

每个采集会话维护：

```text
conversation_id
workflow_record_id
current_dag
confirmed_facts
unresolved_questions
low_confidence_items
current_target
completion_score
recent_turns
conflicts
rules
experience_judgements
entities
artifacts
```

其中：

`current_dag`：

```json
{
  "nodes": [],
  "edges": [],
  "start_node_ids": [],
  "end_node_ids": []
}
```

---

# 13. 节点证据

每个 Node / Edge 必须保留：

- `source_turn_ids`
- `confidence`
- `expert_confirmed`

例如：

```json
{
  "node_id": "n3",
  "node_type": "activity",
  "label": "质量工程师复测",
  "actor_roles": ["质量工程师"],
  "source_turn_ids": ["t8"],
  "confidence": 0.94,
  "expert_confirmed": false
}
```

原则：

> 模型抽取结果 ≠ 已确认事实。

---

# 14. 每轮 LLM 输入

不要把全部历史会话反复给 7B。

推荐：

```text
SYSTEM INSTRUCTION
+
CURRENT DAG SUMMARY
+
CONFIRMED FACTS
+
UNRESOLVED QUESTIONS
+
CURRENT TARGET
+
RECENT 4–6 TURNS
```

如果当前 Graph 很大，给 7B 的不是完整 JSON，而是压缩后的 Graph Summary。

---

# 15. 每轮 LLM 输出协议

推荐：

```json
{
  "assistant_reply": "给专家看的自然语言回复",
  "extracted_facts": [],
  "graph_ops": [
    {
      "op": "add_node",
      "node": {}
    },
    {
      "op": "add_edge",
      "edge": {}
    }
  ],
  "rule_ops": [],
  "judgement_ops": [],
  "entity_ops": [],
  "retry_semantics_ops": [],
  "conflicts": [],
  "unresolved": [],
  "next_question": {
    "target": "parallel_join",
    "priority": "P3",
    "question": "这两个检查完成以后，是各自继续，还是要汇总后再决定下一步？"
  }
}
```

禁止 LLM 直接保存数据库。

所有 Graph Ops 先经过后端 Validator。

---

# 16. Graph Ops

至少支持：

- `add_node`
- `update_node`
- `remove_node`
- `add_edge`
- `update_edge`
- `remove_edge`
- `split_node`
- `merge_nodes`
- `set_start`
- `set_end`
- `set_retry_semantics`

人工在右侧修改 Graph 时，也转换成相同 Graph Ops。

因此：

> LLM 修改与人工修改共用一套变更协议。

---

# 17. DAG Validator

每一次 Graph Ops 合并后执行。

## 必须检查

### ID
- node_id 唯一
- edge_id 唯一

### 引用
- from / to Node 必须存在

### DAG
- 新增 Edge 后不得形成 cycle
- 必须可以拓扑排序

### Start / End
- 至少一个 start
- 至少一个 end
- start 不允许入边
- end 不允许出边

### Decision
- 至少两个 outgoing conditional edges
- 条件不得全部为空

### Parallel Split
- 至少两个 outgoing parallel edges

### Parallel Join
- 至少两个 incoming parallel / merge edges

### Merge
- 至少两个 incoming edges
- 通常一个 outgoing edge

### 孤立节点
- 不允许没有关联的孤立 Node

---

# 18. 如果专家表达形成环怎么办

例如：

> “如果首件不合格，就回去继续调参数，再重新试产。”

模型不能直接创建：

`试产 → 调参`

的反向 Edge。

应生成：

```json
{
  "retry_semantics": {
    "source_node_id": "n9",
    "rework_reference_node_id": "n6",
    "condition": "首件不合格",
    "description": "重新执行参数调整和试产阶段"
  }
}
```

右侧图可以用：

- 虚线提示
- “返工：回到参数调整阶段”文字

但不进入 DAG Edge 集。

---

# 19. 冲突处理

如果出现：

前文：
> “质量主管批准恢复。”

后文：
> “班组长说可以开。”

系统不得覆盖。

生成：

```json
{
  "conflict_type": "approval_owner",
  "candidate_values": ["质量主管", "班组长"]
}
```

下一问：

> “这里我需要确认一下：通常是谁最终有权批准恢复？班组长是建议，还是也有正式批准权？”

---

# 20. 右栏：专家确认视图

右栏不是研究人员调试窗口。

目标是：

> 让制造专家看懂系统目前是怎么理解他的。

因此避免显示：

- node_id
- edge_id
- JSON
- DAG术语
- confidence 数字

默认显示自然语言。

---

# 21. 右栏组成

## A. 实时流程图

默认展示：

- 活动
- 判断
- 并行
- 汇合
- 审批
- 起点 / 终点

颜色区分结构即可。

不使用复杂 BPMN 图标。

## B. 当前结构摘要

显示：

- 制造模式
- 行业
- 流程类型
- 场景
- 当前结构特点

例如：

`条件分支 + 并行处理 + 汇合`

## C. 规则与经验

分开显示：

### 正式规则
连续3件超差 → 通知质量。

### 现场经验
异常持续扩大 → 操作员可能先暂停设备。

## D. 待确认信息

只显示当前最重要的 3–5 项。

不要让专家看到几十条缺失字段。

---

# 22. 右栏纠错

点击 Node 后专家可以：

- “这一步不对”
- 修改文字
- 修改角色
- 删除
- 指出前后关系错误

点击 Branch：

- 修改条件

点击并行结构：

- 改成先后执行
- 改成并行

点击汇合：

- 指定是否必须全部完成

人工修改生成 Graph Ops，并标记：

`expert_confirmed = true`

---

# 23. 采集完成度

不能用“问了几轮”判断。

推荐 Completion Score：

| 维度 | 权重 |
|---|---:|
| Trigger | 10% |
| 主干 | 20% |
| Branch 条件 | 15% |
| Parallel / Merge | 15% |
| Actor / Handoff | 10% |
| System / Artifact | 5% |
| Rule / Judgement | 10% |
| End Condition | 10% |
| Expert Confirmation | 5% |

说明：

如果流程本身没有 Branch 或 Parallel：

- 不扣分；
- 权重重新分配到主干和 End Condition。

---

# 24. 完成门槛

最少：

- Trigger
- Start
- 至少 4 个有效业务 Node
- 有主要 Actor
- 有 End

如果存在 Decision：

- 条件必须明确

如果存在 Parallel：

- Parallel Split / Join 必须闭合

如果专家明确提到返工：

- 必须记录 retry_semantics

建议：

`Completion Score >= 80`

进入最终确认。

---

# 25. 最终确认

主栏停止主动扩展流程，改为：

> “我已经整理出这张流程。请你最后看一下：有没有哪一步顺序不对、哪个分支条件不准确、哪些工作其实不是同时进行？”

右栏显示最终 DAG。

最终确认至少包含：

- 主路径
- 分支
- 并行
- 汇合
- 审批 / 交接
- 规则
- 经验
- 返工语义
- End Condition

按钮：

- `确认并提交`
- `继续修改`

---

# 26. 提交后保存

至少保存四份：

1. `raw_transcript`
2. `dag_graph_json`
3. `normalized_graph_json`
4. `conversation_extraction_trace`

同时：

```text
status = expert_confirmed
expert_confirmed = true
schema_version = 2.0
graph_type = dag
```

---

# 27. 与 Graph-based Workflow Schema v2 的关系

专家采集层使用 Schema v2 的 DAG Profile。

即：

允许：

- start
- activity
- decision
- parallel_split
- parallel_join
- merge
- approval
- handoff
- wait
- end

Edge 不允许形成 cycle。

对于 v2 Schema 中更宽泛的 `directed_graph`：

- 公共信息抽取
- 历史真实日志
- 特殊实验

仍可使用。

但：

> **专家会话采集默认统一输出 DAG。**

这样可以显著降低实验数据表示不一致。

---

# 28. 与数据集页面的衔接

提交后自动进入：

`Expert Collected Dataset`

数据集页面展示：

- DAG Node 数
- Edge 数
- Branch 数
- Parallel 数
- Merge 数
- Retry Semantics 数
- Gold / Expert Confirmed 状态

专家集和公共集仍然分开。

---

# 29. 与 Dashboard 的衔接

Dashboard 增加专家会话采集指标：

- 平均会话轮次
- 平均 Node 数
- 平均 Edge 数
- 含 Branch %
- 含 Parallel %
- 含 Merge %
- 含 Retry Semantics %
- Expert Confirmed %
- 冲突澄清次数
- 平均修改次数

这能判断：

> 数据是不是被采成了大量简单线性流程。

---

# 30. 与实验中心的衔接

专家采集 DAG 可直接生成四种实验输入：

1. `Raw Conversation`
2. `Text Serialization`
3. `Sequence Projection`
4. `Node/Edge DAG`

对应 Gold：

- Gold Nodes
- Gold Edges
- Gold Conditions
- Gold Roles
- Gold Structure

建议实验指标：

### Node
- Precision
- Recall
- F1

### Edge
- Precision
- Recall
- F1

### Branch
- Condition Accuracy

### Parallel
- Parallel Split Detection
- Parallel Join Detection

### Merge
- Merge Accuracy

### Graph
- Structural F1
- Graph Edit Distance
- Path Similarity
- Reachability Consistency

---

# 31. 前端实现建议

推荐：

- React
- React Flow

右侧 Graph 使用自动布局：

- Dagre
- ELK.js

推荐优先：

> React Flow + ELK.js

因为复杂分支和并行结构后，ELK 对层级 DAG 布局通常更合适。

专家默认不需要手动画节点。

Graph 每次更新后自动布局。

但应保留专家手动拖动后的：

`manual_position`

避免每次更新图都跳动过大。

---

# 32. 后端核心接口建议

## 会话

`POST /api/expert-workflows`

新建流程。

`GET /api/expert-workflows`

左栏流程列表。

`GET /api/expert-workflows/{id}`

恢复流程与会话。

`POST /api/expert-workflows/{id}/turns`

发送专家回答。

返回：

```json
{
  "assistant_reply": "...",
  "graph_patch_result": {},
  "current_dag": {},
  "completion": {},
  "unresolved": []
}
```

## Graph

`PATCH /api/expert-workflows/{id}/graph`

人工修图。

`POST /api/expert-workflows/{id}/validate`

完整 DAG 校验。

`POST /api/expert-workflows/{id}/confirm`

专家最终确认。

---

# 33. LLM 服务建议

7B 服务输入不要直接依赖前端。

统一由后端组装：

```text
role_instruction
schema_constraints
current_dag_summary
confirmed_facts
unresolved
current_target
recent_turns
```

输出严格走结构化 JSON。

LLM temperature 建议：

`0.0–0.2`

优先稳定性，不追求创意。

---

# 34. MVP 优先级

## Phase A

必须实现：

- 三栏界面
- 历史流程
- 会话
- DAG Node / Edge
- Decision
- Branch
- Parallel Split / Join
- Merge
- 实时右栏图
- DAG Validator
- Expert Confirmation

## Phase B

增加：

- Rule
- Experience Judgement
- Artifact
- Handoff
- Approval
- Retry Semantics
- 会话冲突处理

## Phase C

增加：

- 自动质量评估
- Gold Annotation
- 多专家复核
- 数据集版本
- 实验直接联动

---

# 35. 开发验收标准

## 专家体验

- 不出现强制 DAG / BPMN 术语
- 专家可以只用自然语言完成采集
- 分支、并行、汇合能够被正确追问
- 右侧实时图专家能看懂
- 专家可以纠正错误

## 数据

- 输出是合法 DAG
- 可以拓扑排序
- Decision 分支条件可追溯
- Parallel Split / Join 成对合理
- 不允许孤立 Node
- 所有自动抽取都有证据 Turn
- 返工不破坏 DAG

## AI

- 不静默补写事实
- 不静默解决冲突
- 低置信度信息进入待确认
- 每轮只问最重要的 1 个主问题

## 研究

- 可直接进入 Expert Dataset
- 可生成 Sequence / Text / DAG 多种实验表示
- 可计算 Node / Edge / Structural 指标
- 可追溯数据版本与专家确认状态

---

# 36. 最终产品心智

专家看到的是：

> “我把平时怎么做工作讲给系统听，系统帮我画出来，我看对不对。”

研究系统看到的是：

> Conversation → Facts → Graph Ops → Validated DAG → Expert Confirmation → Dataset → Experiment

这就是本版本 `conversational_expert_collection` 的核心设计。
