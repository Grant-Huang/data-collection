# 制造协作工作流数据平台设计说明书
## Graph-based Workflow Schema v2 + 会话式专家采集 + 数据集管理 + Dashboard + 实验中心

版本：v2.0  
目标读者：产品经理、前端、后端、算法、数据工程、实验研究人员

---

# 1. 产品目标

本系统用于采集、管理、评估和实验制造业协作工作流数据。

核心目标不是采集“步骤列表”，而是采集真实制造工作中的：

- 活动
- 角色
- 系统与设备
- 信息输入输出
- 判断条件
- 分支
- 并行
- 合并
- 回退 / 循环
- 异常路径
- 审批 / 交接
- 标准规则
- 经验判断
- 过程证据

系统支持两类数据：

1. `public_extracted`：公共信息提取类
2. `expert_collected`：真实专家采集类

两类数据在：
- 数据集管理
- Dashboard
- 实验运行
- 实验结果

中必须分开统计和展示。

---

# 2. 核心模型升级：从 Sequence 到 Directed Workflow Graph

## 2.1 为什么不能只用 DAG

很多制造工作流确实可以表示为 DAG：

- 分支
- 并行
- 汇合

但真实制造流程还经常包含：

- 返工
- 重检
- 不合格返回上一步
- 超时升级
- 异常回退
- 重新排产

因此总体数据模型必须支持：

**Directed Workflow Graph**

并通过 `graph_type` 标记：

- `linear`
- `dag`
- `directed_graph`

## 2.2 Node 类型

至少支持：

- `start`
- `activity`
- `decision`
- `parallel_split`
- `parallel_join`
- `merge`
- `event`
- `wait`
- `approval`
- `handoff`
- `subprocess`
- `end`

说明：

### activity
普通执行动作。

### decision
基于条件选择不同后续路径。

### parallel_split
从一个节点并行启动两个或多个工作。

### parallel_join
等待多个并行工作完成后再继续。

### merge
多个互斥分支重新汇合，不一定要求同时完成。

### handoff
明确表达跨角色 / 跨部门交接。

### approval
审批、放行、授权节点。

### event
事件节点，例如设备报警、客户通知、系统触发。

### wait
等待物料、检测结果、批准、系统反馈等。

### subprocess
引用另一条子流程。

---

# 3. Edge 类型

至少支持：

- `normal`
- `conditional`
- `parallel`
- `merge`
- `loop_back`
- `exception`
- `timeout`
- `handoff`

每条 Edge 可保存：

- condition
- condition_expression
- priority
- source_turn_ids
- confidence
- expert_confirmed

---

# 4. v2 相比 v1 还需要升级的内容

## 4.1 证据可追溯

每一个节点、边、规则、判断都必须能够追溯到：

- 哪一轮会话
- 哪一段公共资料
- 哪一个人工标注

因此统一支持：

- `source_turn_ids`
- `source_reference`

研究人员应可以点击节点，看到原始证据。

## 4.2 置信度

LLM 抽取结果必须保存：

- confidence
- expert_confirmed

不能把模型抽取结果直接等同于事实。

## 4.3 规则与经验分离

必须单独维护：

### rules[]
标准、SOP、制度、法规、系统规则。

### experience_judgements[]
专家在现场形成的经验判断。

这是后续 Workflow Distillation → Experience Distillation 的关键基础。

## 4.4 Artifact / 信息对象

制造工作流不是只传递动作，还会产生和消费：

- 图纸
- 检验结果
- 工单
- 参数
- 报表
- MES记录
- 消息
- CAPA
- 8D报告

因此 v2 增加 `artifacts[]`。

节点可关联：
- input_artifact_ids
- output_artifact_ids

## 4.5 Subgraph / 子流程

复杂工作流允许把一段流程抽成：

- 设备维修子流程
- 质量复测子流程
- ECN审批子流程

支持 `subgraphs[]` 和 `subprocess` 节点。

## 4.6 版本管理

每条 Workflow 必须支持：

- record_version
- status
- updated_at
- history

状态：

- draft
- expert_confirmed
- reviewed
- gold
- rejected

## 4.7 Gold 标注升级

Graph-based Ground Truth 应至少包括：

- Gold Nodes
- Gold Edges
- Gold Roles
- Gold Boundaries
- Gold Conditions

实验不再只比较 Boundary Accuracy。

---

# 5. 专家数据采集总体布局

登录前默认主页面为专家采集。

采用固定竖向三栏：

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 顶部：Logo / 专家采集 / 登录                                        │
├───────────────┬──────────────────────────────┬──────────────────────┤
│ 左栏          │ 主栏                         │ 右栏                 │
│ 历史流程会话  │ 会话式采集                   │ 当前流程图           │
│               │                              │ +结构化摘要          │
│ - 质量异常01  │ AI ↔ 专家                    │ Graph                │
│ - 缺料02      │                              │ 节点/边              │
│ - 换线03      │ 输入框                       │ 待确认项             │
└───────────────┴──────────────────────────────┴──────────────────────┘
```

建议宽度：

- 左栏：240–280px
- 主栏：自适应，最宽
- 右栏：380–460px

---

# 6. 左栏：历史会话 / 已回答流程清单

目的：
让专家能够连续贡献多个流程，并随时回到过去的流程继续补充。

每条显示：

- 流程名称
- 行业 / 场景
- 状态
- 完成度
- 更新时间

例如：

`CNC尺寸超差处理`
- 质量异常
- 82%
- 待确认1项

状态：

- 草稿
- 采集中
- 待确认
- 已确认
- 已提交

功能：

- 新建流程
- 搜索
- 按场景过滤
- 继续上次会话
- 复制已有流程作为新变体
- 删除草稿
- 查看已提交版本

注意：
已提交数据修改后应生成新版本，而不是覆盖历史记录。

---

# 7. 主栏：会话式专家采集

## 7.1 开场原则

不要先问：
- 行业
- 制造类型
- 岗位
- 设备编号

而是先让专家回忆真实案例：

“请回忆一件你亲自参与、比较熟悉的制造工作。可以是异常处理、标准生产、持续改善或工程变更。”

## 7.2 7B 模型职责

仅负责：

1. 引导
2. 复述
3. 澄清
4. 结构化提取

禁止：
- 猜测缺失事实
- 自动补 SOP
- 自动创造角色
- 为了完整性编流程
- 把常识当成专家事实

## 7.3 动态追问逻辑

按信息价值排序：

### P0 主流程骨架
- 什么触发
- 谁开始
- 做什么
- 谁接手
- 如何结束

### P1 Graph 结构
- 是否存在不同分支
- 两件事是否并行
- 多个分支是否重新合并
- 不合格是否回到前面
- 是否存在异常路径 / 超时路径

### P2 判断与经验
- 为什么这么做
- 是标准还是经验
- 判断依据是什么
- 谁拥有最终决定权

### P3 上下文
- 设备
- 系统
- 工序
- 产品
- 物料
- 岗位

### P4 研究增强
- 新手和老手是否不同
- 夜班和白班是否不同
- 不同产品是否有变体
- 是否存在少见但重要的例外

---

# 8. Graph 结构专用追问模板

不要向专家说 DAG、Merge、Parallel Join。

系统内部要把制造语言映射为 Graph 结构。

## 分支

问：
“这里是不是只有一种处理方式？还是不同情况下会走不同方向？”

## 并行

问：
“这两件事是先后做，还是可以同时进行？”

## 合并

问：
“这两个处理完成以后，会不会回到同一个步骤继续？”

## 回路

问：
“如果这次检查还不合格，是流程结束，还是回到前面的某一步重新处理？”

## Exception

问：
“有没有一种少见情况，会跳过正常流程，直接升级给主管或停线？”

---

# 9. 主栏交互

每轮回答后：

1. 7B 生成 assistant_reply
2. 同时生成 extracted_facts
3. 同时生成 json_patch
4. 后端校验
5. 右栏图实时更新

如果模型发现冲突：

例如：
前面说“质量主管批准恢复生产”
后面说“班组长决定恢复”

不允许静默覆盖。

必须追问：

“前面你提到质量主管批准恢复生产，现在又提到班组长决定。通常是谁最终决定？还是不同情况不同？”

---

# 10. 右栏：当前已经整理出的流程

右栏是专家确认机制的核心。

## 10.1 顶部：Graph 图

使用 React Flow / Cytoscape / D3 等实现。

显示：

- 活动节点
- 决策节点
- 并行节点
- 合并节点
- 回路
- 起点终点

视觉上避免 BPMN 过重。

专家看到的文字必须是自然制造语言。

## 10.2 图操作

专家可以：

- 点击节点查看详情
- 标记“这里不对”
- 编辑节点文字
- 拖动布局
- 删除误识别节点
- 修改分支条件
- 合并重复节点

但默认以“看懂 + 纠正”为主，不要求专家自己画图。

## 10.3 结构化摘要

图下方显示：

- 已识别角色
- 已识别设备
- 已识别系统
- 标准规则
- 经验判断
- 尚未确认的信息

例如：

### 已识别规则
连续3件超差 → 通知质量

### 已识别经验
异常持续扩大时 → 操作员可先停机

### 还需确认
- 谁批准恢复生产
- 首件不合格后回到哪一步

---

# 11. 会话状态机

每个会话维护：

- conversation_id
- workflow_record_id
- current_graph
- unresolved_questions
- confirmed_facts
- low_confidence_items
- current_target
- completion_score
- last_n_turns

不要每轮把完整对话全部送给 7B。

推荐输入：

- 最近4–6轮
- 当前 Graph 摘要
- 已确认事实
- 未解决问题
- 当前追问目标

---

# 12. 每轮 LLM 输出协议

```json
{
  "assistant_reply": "...",
  "extracted_facts": [],
  "json_patch": [],
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
  "conflicts": [],
  "unresolved": [],
  "next_question": {
    "target": "edge_condition",
    "priority": "P1",
    "question": "如果首件仍然不合格，会回到哪一步？"
  }
}
```

Graph 修改必须通过后端 Graph Validator。

---

# 13. Graph Validator

导入或会话增量更新时，至少校验：

- node_id 唯一
- edge_id 唯一
- edge 指向节点存在
- start/end 合法
- decision 节点至少两个出口
- parallel_split 至少两个出口
- parallel_join 至少两个入口
- loop_back 明确标记
- 不允许孤立节点
- merge 语义合理
- subprocess 引用存在
- 条件边条件不为空
- expert_confirmed 状态一致

---

# 14. 完成度判断

不能只看“步骤数量”。

建议 Completion Score：

- Trigger 10%
- 主流程骨架 20%
- Graph结构完整 20%
- 角色 10%
- 系统/设备 10%
- 判断条件 10%
- Rule/Judgement 10%
- End Condition 10%

当：
- >= 80：可以进入专家总结确认
- 60–79：提示仍有重要缺口
- <60：继续采集

---

# 15. 最终确认

完成后主栏由“继续追问”切换为“总结确认”。

显示：

- 流程名称
- Graph 图
- 主路径
- 分支
- 并行
- 回路
- 规则
- 经验判断
- 结束条件
- 未确认项

专家点击：

- 正确，提交
- 有问题，继续修改

提交后：

- raw transcript
- graph JSON
- normalized JSON
- expert_confirmed=true
- 保存版本

---

# 16. 数据集页面

登录后可进入。

建议 Tab：

1. 数据集列表
2. 数据浏览
3. 导入
4. 导出
5. 数据评估
6. 版本记录

---

# 17. 数据集列表

分两大类：

## Public Extracted
公共信息提取类。

## Expert Collected
真实专家采集类。

每个数据集显示：

- 名称
- 类型
- 版本
- 样本数
- Graph类型分布
- Gold比例
- Dataset Readiness
- 更新时间
- 推荐用途

---

# 18. 单个数据集详情

建议四个视图：

### Overview
基本统计。

### Records
逐条流程。

### Coverage
行业、制造模式、场景、角色分布。

### Quality
完整度、标注、重复、泄漏风险。

点击任意 Workflow：

左侧 metadata  
中间 Graph  
右侧 provenance / annotation / quality

---

# 19. 导入设计

外部系统按照 Schema v2 导出。

本系统支持 JSON 导入。

导入流程：

1. 上传
2. JSON Schema 校验
3. Graph Validator
4. source_type 检查
5. Provenance 完整性
6. 角色实体完整度
7. Graph结构评估
8. 近重复检查
9. Train/Test Leakage 风险
10. Annotation检查
11. 自动数据集评估
12. 用户确认
13. 正式导入

---

# 20. 导入评估报告

至少显示：

- 总记录数
- 可导入
- 阻断错误
- 警告
- Linear / DAG / Directed Graph 比例
- 平均节点数
- 平均边数
- 平均分支数
- 平均并行结构数
- 平均回路数
- 角色完整率
- 条件完整率
- Provenance完整率
- Gold标注覆盖率
- Readiness Score

自动给出：

- 可用于主实验
- 适合辅助实验
- 需人工复核
- 不建议使用

---

# 21. 导出设计

支持：

- 整个数据集
- 当前筛选
- 指定记录

格式：

- Raw Graph JSON
- Anonymized Graph JSON
- Role-normalized Graph JSON
- Gold Annotation JSON

可筛选：

- source_type
- industry
- manufacturing_mode
- workflow_type
- graph_type
- annotation_status
- recommended_usage

---

# 22. Dashboard 总体设计

Dashboard 登录后可见。

必须支持：

- 专家集
- 公共集

一键切换，默认不得混合统计。

---

# 23. Dashboard 一级指标

顶部：

- 数据集数
- Workflow数
- 专家数
- 公共来源数
- Gold数量
- Dataset Readiness
- 最近新增
- 待复核

---

# 24. Dashboard 数据集八维评估

继续保留：

1. Coverage
2. Balance
3. Completeness
4. Extractability
5. Authenticity
6. Annotation Readiness
7. Diversity
8. Leakage Risk

但 v2 增加 Graph 指标。

---

# 25. Graph-specific 数据质量指标

新增：

## Graph Completeness
- 有明确 start 比例
- 有明确 end 比例
- decision 条件完整率
- parallel join 完整率
- loop_back 条件完整率
- 孤立节点比例

## Structural Diversity
- Linear比例
- DAG比例
- Directed Graph比例
- 含Branch比例
- 含Parallel比例
- 含Loop比例
- 含Exception比例

## Graph Complexity
- 平均节点数
- 平均边数
- 平均分支数
- 最大深度
- 并行宽度
- Loop数量
- Subgraph数量

---

# 26. Dataset Readiness Score v2

建议：

- Coverage 15%
- Balance 10%
- Completeness 15%
- Graph Completeness 15%
- Extractability 10%
- Authenticity 10%
- Annotation Readiness 10%
- Diversity 5%
- Structural Diversity 5%
- Leakage Risk 5%

仍然强调：
总分只是概览，不能替代明细。

---

# 27. 实验中心

实验中心登录后进入。

每个实验首先必须选择：

### 数据源
- Public
- Expert

### 数据集

### Split
- Train
- Validation
- Test

### 输入版本
- Raw
- Anonymized
- Role-normalized

### Graph表示
- Sequence Projection
- Node/Edge Graph
- Event Log
- Text Serialization

### Gold Annotation
- Nodes
- Edges
- Boundary
- Roles
- Conditions

---

# 28. 两类数据必须分开跑

默认规则：

Public → 单独实验  
Expert → 单独实验

允许：

Combined Train

但 Test 仍必须分别：

- Public Test
- Expert Test

最终报告必须并排显示。

禁止只报告一个混合总分。

---

# 29. Graph-based 实验指标

除了原来的 Boundary Accuracy，还应增加：

## Node
- Node Precision
- Node Recall
- Node F1

## Edge
- Edge Precision
- Edge Recall
- Edge F1

## Branch
- Branch Condition Accuracy

## Parallel
- Parallel Structure Accuracy

## Merge
- Merge Accuracy

## Loop
- Loop Detection F1

## Role
- Role Assignment Accuracy

## Graph-level
- Graph Edit Distance
- Path Similarity
- Reachability Consistency
- Structural F1

## Downstream
- Process Discovery Quality
- Conformance Fitness
- Precision
- Generalization

---

# 30. 实验参数 UI

沿用横向动态实验卡片设计。

每张实验卡固定宽度。

屏幕默认显示 4–5 个。

支持横向滚动。

右侧固定：

`+ 新增实验`

每张卡至少包含：

- Experiment Name
- Dataset
- Source Type
- Representation
- Model
- Prompt / Method
- Parameters
- Seed
- Run
- Status

---

# 31. 结果页面

结果不要只显示一个表。

建议四层：

## Summary
总体指标。

## Graph
结构指标。

## Error Analysis
典型失败案例。

## Dataset Slice
按以下维度切片：

- 行业
- 制造模式
- 场景
- Workflow Type
- Graph Type
- Graph Complexity
- Public vs Expert

---

# 32. 后端核心服务

建议服务划分：

## Conversation Service
管理专家会话。

## LLM Guide Service
7B 引导模型。

## Graph Extraction Service
文本 → Graph Ops。

## Graph Validation Service
Graph合法性。

## Dataset Service
数据集版本、导入导出。

## Quality Service
数据评估。

## Experiment Service
实验运行。

## Annotation Service
Gold标注与仲裁。

---

# 33. 推荐数据库对象

至少：

- users
- experts
- conversations
- conversation_turns
- workflow_records
- workflow_versions
- graph_nodes
- graph_edges
- entities
- rules
- judgements
- artifacts
- datasets
- dataset_records
- annotations
- import_jobs
- export_jobs
- quality_reports
- experiments
- experiment_runs
- experiment_results

Graph 节点/边可以关系表存储，也可整体 JSONB 保存。
建议：
- JSONB 保存完整版本快照
- 关系表支持查询分析

---

# 34. 权限

专家：
- 创建/修改自己的草稿
- 查看自己的历史流程
- 提交
- 修改需生成新版本

研究员：
- 查看数据集
- 导入导出
- 数据评估
- 创建实验
- 标注

管理员：
- 用户
- 权限
- 数据集发布
- Gold版本
- 删除 / 归档

---

# 35. 审计

必须记录：

- 谁修改了哪个节点
- 修改前后
- LLM自动修改还是人工修改
- 谁确认
- 谁标注Gold
- 哪个实验用了哪个版本数据

保证实验可复现。

---

# 36. MVP 开发优先级

## Phase 1
- 三栏专家采集
- 7B引导
- Graph Nodes/Edges
- Branch/Loop
- 实时右栏图
- 标准JSON v2
- Expert数据集

## Phase 2
- Parallel/Merge
- Rule/Judgement
- 数据集导入导出
- Dashboard v2
- Public数据集

## Phase 3
- Gold Annotation
- 数据质量评分
- Leakage检测
- 实验中心Graph指标
- Error Analysis

## Phase 4
- Subgraph
- 多专家复核
- 自动经验模式抽取
- Workflow → Pattern → Skill

---

# 37. 验收标准

专家采集：
- 专家不需要学习DAG/BPMN术语
- 能通过会话表达分支、并行、合并、回路
- 右栏Graph实时更新
- 所有自动抽取均可追溯原会话
- 不允许LLM静默补写事实

数据：
- 可导入/导出Schema v2
- Public/Expert明确区分
- 数据版本可追溯
- Graph Validator可阻断结构错误

Dashboard：
- 八维质量 + Graph质量
- 可以定位具体问题样本

实验：
- 两类数据分开跑
- Graph结构指标可计算
- 每个结果可追溯到数据集版本、参数、seed

---

# 38. 最终产品结构

```text
专家采集
  ├─ 历史会话
  ├─ 会话采集
  └─ 实时Graph确认

数据集
  ├─ Public
  ├─ Expert
  ├─ 导入
  ├─ 导出
  ├─ 版本
  └─ 质量评估

Dashboard
  ├─ Coverage
  ├─ Balance
  ├─ Completeness
  ├─ Graph Quality
  ├─ Annotation
  └─ Leakage

实验中心
  ├─ Dataset Selection
  ├─ Representation
  ├─ Methods
  ├─ Graph Metrics
  ├─ Error Analysis
  └─ Reproducibility
```

这四部分共享同一套 Graph-based Workflow Schema v2。