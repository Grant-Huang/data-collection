# 两阶段论文结构（DAG / Reusable Operational Subgraph 版）

## 总体研究主线

原来的两篇论文主线是：

> Collaborative Work Trace → Episode Segmentation → Micro-workflow Discovery → Skill Evolution / Composition

加入分叉、并行、汇合后，建议升级为：

> Collaborative Work Trace → Work Graph Reconstruction → Work-Unit Partitioning → Reusable Operational Subgraph Distillation → Executable Skill Compilation → Hierarchical Composition & Evolution

核心变化不是“给序列增加几个分支”，而是研究对象发生了变化：

> **Micro-workflow 不再定义为 reusable sequence，而定义为 reusable operational subgraph。**

形式上：

\[
MW=(V,E,\Gamma,I,O)
\]

其中：

- \(V\)：活动 / semantic capability 节点；
- \(E\)：工作依赖关系，而不是简单时间先后；
- \(\Gamma\)：控制关系，如 Sequence / XOR / AND / OR / Join policy；
- \(I\)：触发条件、输入对象、前置条件；
- \(O\)：输出、后置状态、可验证结果。

这样可以同时覆盖：

- 传统线性处理套路；
- 多 Agent 并行调查；
- 人与 Agent 分工；
- 条件选择；
- 多支路汇合；
- 非连续、时间交错的工作单元。

---

# Paper 1

## 建议标题

**Collaborative Workflow Distillation: Discovering Reusable Operational Subgraphs from Human–Agent Manufacturing Work Traces**

可选副标题：

**From Temporal Event Traces to Dependency-Aware Work Graphs**

中文概括：

> 从人—Agent制造协作轨迹中发现可复用运营子图。

---

## Paper 1 核心问题

第一篇不再主要回答“长序列怎么切”，而是回答：

> **如何从低层、异构、并行、交错的人—Agent协作事件中，恢复真实工作依赖，并蒸馏出稳定、可复用的运营子图？**

因此研究对象从：

`Event Sequence`

升级为：

`Collaborative Work Graph`。

---

## Paper 1 的三个核心概念贡献

### 1. Manufacturing Operational Work Graph

传统制造日志主要记录：

- Production Order；
- Machine event；
- Material movement；
- Transaction；
- Process state。

AgentNexus类协作平台额外记录：

- investigation；
- evidence collection；
- handoff；
- message / thread；
- tool call；
- delegation；
- approval；
- retry；
- human intervention；
- task dependency。

因此提出：

> **Manufacturing Operational Work Graph**：描述制造问题是如何被人、Agent与企业系统共同理解、调查、决策和处置的工作图。

一个事件节点保存：

\[
Event=(Actor,Action,Intent,Object,Tool,Time,Result)
\]

事件之间不只记录：

\[
TemporalOrder
\]

还记录：

\[
WorkDependency
\]

例如：

- depends-on；
- fork；
- join；
- approval-before；
- retry-of；
- spawned-by；
- evidence-for。

### 2. Work-Unit Partitioning beyond Exact Boundaries

在线性流程中，可用 episode boundary 表示工作单元。

但在并行协作中：

- 设备调查可能是步骤 3、5、9；
- 计划评估可能是步骤 4、7；
- 质量检查可能是步骤 6、8。

因此 Episode 不能再定义成：

\[
[start,end]
\]

而应定义为：

\[
Episode \subseteq V
\]

即一个事件集合 / 子图。

由此论文中的实验观点升级为：

> **Exact Boundary Accuracy is insufficient for graph-structured collaborative work.**

需要同时评价：

- Boundary F1（用于线性兼容）；
- Episode Membership ARI；
- NMI；
- Pairwise Membership F1；
- Segment Purity；
- Fragmentation；
- Merge Rate。

### 3. Reusable Operational Subgraph Distillation

候选微工作流不是简单 frequent sequence，而是：

> 在不同 case、场景、角色、工具和执行顺序下仍保留稳定目标、核心 capability 与依赖结构的 reusable operational subgraph。

即：

\[
Repeated\ Work\ Graphs
\rightarrow
Semantic\ Abstraction
\rightarrow
Work\ Unit\ Partition
\rightarrow
Subgraph\ Alignment
\rightarrow
Reusable\ Operational\ Subgraph
\]

---

## Paper 1 研究问题（更新版）

### RQ1 — Work Graph Recoverability

能否从人—Agent制造协作轨迹中恢复稳定的工作依赖结构，而不是仅依赖时间顺序？

关注：

- dependency edge recovery；
- fork recovery；
- join recovery；
- branch type recovery。

### RQ2 — Work-Unit Partitioning

当协作事件存在时间交错和并行时，dependency-aware / semantic graph partition 是否优于纯 change-point segmentation？

关注：

- Exact Boundary F1；
- Tolerant Boundary F1；
- ARI；
- NMI；
- Pairwise Membership F1；
- downstream subgraph recovery。

### RQ3 — Reusable Subgraph Discovery

是否可以从不同执行变体中发现稳定的 reusable operational subgraphs？

关注：

- node recovery；
- dependency edge recovery；
- fork/join recovery；
- structural similarity；
- micro-workflow identity recovery。

### RQ4 — Robustness

在以下变化下是否仍能恢复：

- business variation；
- execution deviation；
- logging imperfection；
- temporal interleaving；
- actor substitution；
- tool heterogeneity；
- cross-workflow contamination。

### RQ5 — Reusability / Generalization

发现的子图是否：

- 跨 Case 重复；
- 跨 Scenario 重复；
- 跨 Tool 重复；
- 跨 Actor 重复；
- 能解释 unseen workflow compositions？

### RQ6 — Prospective Utility（轻量）

检索到的 reusable operational subgraph 是否能作为未来任务的 procedural guidance？

只做 retrieval-assisted execution，不做优化与自演化。

---

## Paper 1 建议章节结构

### 1. Introduction

主线：

1. Manufacturing event logs只能看到“发生了什么”；
2. Human-Agent协作平台开始记录“问题是如何被处理的”；
3. 这些协作工作不是简单线性流程，而包含分支、并行、汇合和动态人机协作；
4. 现有 process mining / agent workflow memory 多围绕 transaction traces 或 tool-use sequence；
5. 我们提出 Collaborative Workflow Distillation，从协作事件图中发现 reusable operational subgraphs。

### 2. Related Work

建议分五组：

2.1 Process Mining and Manufacturing Event Logs  
2.2 Event Abstraction and Object-Centric Process Mining  
2.3 Agent Workflow / Experience Memory  
2.4 Workflow Discovery and Optimization (AFlow / FlowScout 等)  
2.5 Human-Agent Collaboration Traces and Research Gap

Research Gap 要明确：

> 现有研究尚未充分解决“从持续的人—Agent协作工作图中发现可复用运营能力单元”的问题，尤其缺乏对 dependency、parallelism、human handoff 和 reusable subgraph 的统一建模。

### 3. Problem Formulation

3.1 Manufacturing Operational Work  
3.2 Collaborative Work Trace  
3.3 Collaborative Work Graph  
3.4 Work Dependency vs Temporal Order  
3.5 Work Unit / Episode as Event Subset  
3.6 Reusable Operational Subgraph Definition

### 4. Method

4.1 Work Trace Ingestion  
4.2 Semantic Capability Abstraction  
4.3 Dependency Reconstruction  
4.4 Graph-Aware Work-Unit Partitioning  
4.5 Candidate Subgraph Alignment / Clustering  
4.6 Consensus Operational Subgraph Mining  
4.7 Reusability Qualification  
4.8 Expert Review and Provenance

### 5. Experimental Design

5.1 Ground-truth Work Graph Simulator  
5.2 Sequence vs DAG Conditions  
5.3 Segmentation / Partitioning Baselines  
5.4 PM4Py Inductive / Heuristics Baselines  
5.5 Dependency-Graph Baseline  
5.6 Disturbance Ablation  
5.7 Parallelism / Interleaving Sensitivity  
5.8 Tool / Actor Heterogeneity  
5.9 Held-out Composition Generalization  
5.10 Expert Wizard / Real Trace Validation  
5.11 Prospective Retrieval Utility

### 6. Results

建议不要按算法模块组织，而按 RQ 组织：

6.1 Can work dependencies be recovered?  
6.2 Does graph-aware partitioning outperform temporal segmentation?  
6.3 Can reusable operational subgraphs be recovered?  
6.4 What kinds of disturbance hurt most?  
6.5 Are discovered subgraphs reusable across contexts?  
6.6 Does retrieval provide procedural value?

### 7. Discussion

7.1 Exact Boundary Accuracy vs Work-Unit Utility  
7.2 Temporal Sequence Is Not Work Dependency  
7.3 Why Reusable Subgraphs Are Stronger than Frequent Sequences  
7.4 Implications for Manufacturing Process Mining  
7.5 Implications for Human-Agent Collaboration Platforms  
7.6 Limitations

### 8. Conclusion

结论边界：

> Paper 1 证明“组织日常协作轨迹中可以发现稳定的 reusable operational subgraphs”，但不宣称这些子图已经自动成为最优、可执行、可组合的技能。

---

# Paper 2

## 建议标题

**From Reusable Operational Subgraphs to Self-Evolving Manufacturing Skills: Execution-Guided Compilation, Composition, and Governance**

或更强调组织能力：

**From Collaborative Work Graphs to Organizational Skills: Hierarchical Composition and Execution-Guided Evolution in Manufacturing**

中文概括：

> 从可复用运营子图到可执行、可组合、可演化的制造组织技能。

---

## Paper 2 核心问题

第一篇解决：

> 哪些工作结构值得沉淀？

第二篇解决：

> **如何把这些被发现的 reusable subgraphs 编译成可执行 Skill，并在未来任务中动态组合、验证、修正和演化？**

因此第二篇研究对象不再是 raw trace，而是：

\[
Validated\ Operational\ Subgraph
\rightarrow
Executable\ Skill
\]

---

## Paper 2 的核心概念

### 1. Executable Manufacturing Skill

Skill 不等于历史 workflow graph。

应包含：

\[
Skill=(Goal,Interface,Preconditions,Graph,Postconditions,Policy,Metrics,Provenance)
\]

其中：

- Goal；
- Inputs / Objects；
- Preconditions；
- executable workflow graph；
- branch / join semantics；
- outputs；
- postconditions；
- permissions；
- human approval points；
- expected cost / duration；
- reliability；
- provenance / version。

### 2. Skill Graph / Organizational Capability Graph

技能之间存在：

- prerequisite；
- produces-for；
- alternative-to；
- refines；
- contains；
- compatible-with；
- conflicts-with。

形成：

> Manufacturing Skill Graph。

### 3. Hierarchical Composition

未来复杂任务不是从原子 Tool Call 开始规划，而是优先选择稳定 Skill：

\[
Goal
\rightarrow
Skill\ Planning
\rightarrow
Subskill\ Expansion
\rightarrow
Tool\ Execution
\]

对应“Deterministic Small / Agentic Large”：

- 小的已验证 Skill 尽量稳定；
- 大任务组合保留 Agentic flexibility。

### 4. Execution-Guided Evolution

历史频繁不等于最优。

因此技能执行后根据：

- success / failure；
- retries；
- human correction；
- cost；
- latency；
- outcome quality；
- safety / governance signals

持续更新。

机制可参考：

- MCTS；
- candidate mutation；
- branch replacement；
- alternative skill selection；
- version promotion / rollback。

---

## Paper 2 研究问题

### RQ1 — Skill Compilation

能否将 Paper 1 发现的 operational subgraph 转换成稳定、可执行、具有明确接口的 Skill？

### RQ2 — Hierarchical Composition

以 validated skills 作为规划单元，是否比直接从原子 tool calls 规划：

- 更高成功率；
- 更少步骤；
- 更低搜索复杂度；
- 更强跨场景泛化？

### RQ3 — Parallel Composition

Skill planner 能否正确组合包含：

- sequence；
- XOR；
- AND；
- OR；
- human approval；
- synchronization barrier

的复杂工作图？

### RQ4 — Execution-Guided Evolution

执行反馈是否能持续改进：

- routing；
- branch conditions；
- optional steps；
- fallback；
- escalation；
- skill ranking？

### RQ5 — Negative Transfer / Governance

错误或过期 Skill 如何：

- 降权；
- 隔离；
- 回滚；
- 废弃；
- 保持版本与审计？

### RQ6 — Organizational Knowledge Retention

技能库是否可以把个人/Agent的工作经验转化成跨人员、跨时间可复用的组织能力？

---

## Paper 2 建议章节结构

### 1. Introduction

从 Paper 1 的限制切入：

> Discovery is not execution. A historically recurring operational subgraph does not automatically constitute a safe, reliable, or optimal skill.

提出：

> execution-ready organizational skill compilation and evolution。

### 2. Related Work

2.1 Agent Workflow Optimization  
2.2 Agent Workflow Memory / Skill Memory  
2.3 Hierarchical Planning / HTN  
2.4 Workflow Composition  
2.5 Self-Evolving Agents  
2.6 Enterprise / Manufacturing Governance

### 3. Skill Model

3.1 Operational Subgraph Input  
3.2 Skill Interface  
3.3 Preconditions / Postconditions  
3.4 Branch / Join Execution Semantics  
3.5 Human Approval  
3.6 Reliability / Cost / Provenance

### 4. Skill Compilation

4.1 Normalize Graph  
4.2 Identify Required / Optional Nodes  
4.3 Infer Preconditions  
4.4 Infer Outputs / Postconditions  
4.5 Map Capabilities to Executable Tools  
4.6 Validation / Sandbox Execution  
4.7 Skill Version Creation

### 5. Hierarchical Composition

5.1 Skill Retrieval  
5.2 Goal-to-Skill Planning  
5.3 Parallel Skill Scheduling  
5.4 Synchronization / Join Semantics  
5.5 Human-in-the-loop Nodes  
5.6 Fallback to Lower-Level Planning

### 6. Execution-Guided Evolution

6.1 Feedback Signals  
6.2 Candidate Workflow Mutation  
6.3 Search / MCTS / Alternative Exploration  
6.4 Promotion Rules  
6.5 Rollback / Deprecation  
6.6 Negative Transfer Control

### 7. Experiments

7.1 Skill Compilation Fidelity  
7.2 Atomic Planning vs Skill Planning  
7.3 Seen vs Unseen Compositions  
7.4 Sequential vs Parallel Tasks  
7.5 Human Approval / Exception Cases  
7.6 Execution Feedback Ablation  
7.7 Evolution Over Repeated Tasks  
7.8 Bad Skill / Stale Skill Injection  
7.9 Real AgentNexus Longitudinal Evaluation

### 8. Results

按问题而不是模块组织。

### 9. Discussion

重点讨论：

- organizational skill vs agent memory；
- stable skill vs flexible planning；
- experience accumulation；
- governance；
- organizational capability retention。

### 10. Conclusion

最终主张：

> Human–Agent collaborative experience can be transformed from observed work graphs into governed, executable organizational skills that can be recombined and improved through future execution.

---

# 两篇论文之间的明确边界

| 问题 | Paper 1 | Paper 2 |
|---|---|---|
| 原始 Human-Agent trace | 核心 | 输入来源说明 |
| Semantic abstraction | 核心 | 直接使用 |
| Temporal vs dependency graph | 核心 | 直接使用 |
| Episode / work-unit discovery | 核心 | 不再研究 |
| Reusable subgraph discovery | 核心 | 输入 |
| Fork / join recovery | 核心 | 执行语义 |
| Reusability validation | 核心 | 使用 |
| Workflow execution | 轻量 retrieval utility | 核心 |
| Skill interface | Future work | 核心 |
| Preconditions / postconditions | Future work | 核心 |
| Dynamic composition | 不做 | 核心 |
| MCTS / workflow evolution | 不做 | 核心 |
| Version / rollback / governance | 不做 | 核心 |
| Long-term organizational skill library | 讨论 | 核心贡献 |

---

# 最终统一研究叙事

两篇论文组合起来形成一条完整但边界清楚的研究链：

\[
Raw\ Collaborative\ Work
\]

\[
\downarrow
\]

\[
Collaborative\ Work\ Graph
\]

\[
\downarrow
\]

\[
Reusable\ Operational\ Subgraph
\]

**Paper 1 到此结束。**

\[
\downarrow
\]

\[
Executable\ Skill
\]

\[
\downarrow
\]

\[
Hierarchical\ Composition
\]

\[
\downarrow
\]

\[
Execution\ Feedback
\]

\[
\downarrow
\]

\[
Skill\ Evolution\ +\ Governance
\]

**Paper 2 到此完成。**

从理论上，这比原来的“微工作流抽取 + 大工作流组合”更加准确：

> 第一篇研究的是 **组织工作结构如何被发现**；
>
> 第二篇研究的是 **被发现的组织工作结构如何变成可执行、可组合、可演化的组织能力**。
