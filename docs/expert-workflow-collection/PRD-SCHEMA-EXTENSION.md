# Schema 扩展设计文档：时间约束和评估规则结构化

版本：v0.1  
日期：2026-10-07  
相关 Issue：时间信息和规则信息的结构化表示

---

## 背景

原有 Schema 对节点的时间约束和决策规则的表示不够结构化：

- `expected_duration`：字符串形式（"2h"），无法表现 deadline 类型、起算时点、是否强制等语义
- `decision_criteria`：数组的字符串，无法表现指标定义、阈值、逻辑关系等细节

这导致采集的工作流数据缺少制造业专家常见的**时间约束（SLA/deadline）** 和 **决策规则** 信息。

真实例子（来自精密加工质量异常处理）：

> 分完类，值班工程师两个小时之内要做初评，看缺陷密度、看落在哪个 die、是否关键层。

这句话包含：
1. 执行人：值班工程师
2. 时间约束：2 小时内（硬性 deadline）
3. 评估项：缺陷密度（带阈值）、die 位置（分类）、关键层标记（是否）

---

## 设计原则

1. **向后兼容**：保留原有的 `expected_duration` 和 `decision_criteria` 字段，新字段为可选扩展
2. **结构化但不过度**：新字段提供结构化的能力，但不强制所有工作流都填满所有细节
3. **易于人工标注**：采集系统中，LLM 可以把自然语言转成这些结构化字段
4. **支持后续分析**：Dashboard/实验中心可以基于这些结构化信息做时间分析、规则挖掘

---

## Phase 1：Schema 扩展（已完成）

### 1.1 新增字段：`sla_config`

在 node 对象中新增，定义节点的服务级别协议配置。

**JSON Schema 定义**：

```json
{
  "sla_config": {
    "type": "object",
    "properties": {
      "type": {
        "enum": ["deadline", "target", "warn_threshold"],
        "description": "SLA 类型：
          - deadline: 硬性截止时间，超期会导致流程异常
          - target: 目标时长，仅作参考，不强制
          - warn_threshold: 预警阈值，接近时提醒"
      },
      "duration": {
        "type": "string",
        "description": "ISO 8601 格式（如'PT2H'）或自然语言（如'2h'）"
      },
      "from_trigger": {
        "enum": ["previous_node_completed", "workflow_start", "manual_start"],
        "description": "时间计算的起点：
          - previous_node_completed: 从前序节点完成开始
          - workflow_start: 从工作流开始
          - manual_start: 从手动开始（人手动点击开始按钮）"
      },
      "enforced": {
        "type": "boolean",
        "description": "是否为硬性约束"
      },
      "violation_action": {
        "enum": ["escalate", "notify", "auto_reassign", "none"],
        "description": "超期时的处理方式"
      },
      "description": {
        "type": "string",
        "description": "人类可读的说明"
      }
    }
  }
}
```

**使用例**（"2小时内完成初评"）：

```json
{
  "node_id": "n_initial_review",
  "label": "初评",
  "expected_duration": "2h",
  "sla_config": {
    "type": "deadline",
    "duration": "PT2H",
    "from_trigger": "previous_node_completed",
    "enforced": true,
    "violation_action": "escalate",
    "description": "必须在前序节点完成后2小时内完成初评"
  }
}
```

### 1.2 新增字段：`evaluation_criteria`

在 node 对象中新增，取代简单的 `decision_criteria`。

**JSON Schema 定义**：

```json
{
  "evaluation_criteria": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["id", "name", "type"],
      "properties": {
        "id": {
          "type": "string",
          "description": "唯一标识符（供后续引用）"
        },
        "name": {
          "type": "string",
          "description": "人类可读的名称"
        },
        "type": {
          "enum": ["metric", "categorical", "boolean", "text", "numeric_range"],
          "description": "数据类型"
        },
        "required": {
          "type": "boolean",
          "description": "是否必填"
        },
        "unit": {
          "type": "string",
          "description": "单位（如'defects/mm²'、'%'）"
        },
        "thresholds": {
          "type": "object",
          "description": "数值型指标的阈值定义",
          "properties": {
            "normal": {"type": "string"},
            "warning": {"type": "string"},
            "critical": {"type": "string"}
          }
        },
        "allowed_values": {
          "type": "array",
          "description": "分类型指标的允许值列表"
        },
        "logic": {
          "enum": ["AND", "OR"],
          "description": "与下一个标准的逻辑关系"
        },
        "depends_on": {
          "type": "string",
          "description": "依赖的前置标准 id"
        },
        "description": {
          "type": "string",
          "description": "评估方法说明"
        }
      }
    }
  }
}
```

**使用例**（"缺陷密度、die位置、关键层"）：

```json
{
  "node_id": "n_initial_review",
  "label": "初评",
  "evaluation_criteria": [
    {
      "id": "defect_density",
      "name": "缺陷密度",
      "type": "metric",
      "required": true,
      "unit": "defects/mm²",
      "thresholds": {
        "normal": "< 10 defects/mm²",
        "warning": "10-20 defects/mm²",
        "critical": "> 20 defects/mm²"
      },
      "logic": "AND",
      "description": "检查单位面积内的缺陷数量"
    },
    {
      "id": "die_location",
      "name": "Die 位置",
      "type": "categorical",
      "required": true,
      "allowed_values": ["core", "periphery", "edge"],
      "logic": "AND",
      "description": "缺陷落在芯片哪个区域"
    },
    {
      "id": "critical_layer",
      "name": "关键层标记",
      "type": "boolean",
      "required": true,
      "logic": "AND",
      "description": "是否落在关键工艺层"
    }
  ]
}
```

### 1.3 向后兼容性

- 原有的 `expected_duration` 字段继续保留，标记为"已弃用，保留向后兼容"
- 原有的 `decision_criteria` 字段继续保留，作为"简单文本形式的标准"
- 新系统优先使用 `sla_config` 和 `evaluation_criteria`，但对仅包含旧字段的数据仍然支持解析

---

## Phase 2：UI 可视化（规划中，待实现）

### 2.1 DAG 图层（第 11 节延伸）

在节点上展示 SLA 信息：

```
┌─────────────┐
│   初评      │
│ 值班工程师  │
│ ⏱ 2h SLA   │  ← 新增 SLA 标签
└─────────────┘
```

样式规范（参考 PRD 第 11.3 节）：

- 时钟图标 + "2h" 文字，放在节点下方
- 硬性 deadline：深红色边框
- 目标时长：橙色边框
- 预警阈值：黄色边框

### 2.2 节点详情面板（第 11.4 节延伸）

点击节点后展示完整的 SLA 和评估规则：

```
┌──────────────────────────────────────┐
│  初评                                 │
├──────────────────────────────────────┤
│ 时间约束:                             │
│  • 类型: 硬性 Deadline                │
│  • 时长: 2 小时                       │
│  • 起点: 从前序节点完成开始            │
│  • 超期处理: 升级                     │
│  说明: 必须在分类完成后...             │
│                                      │
│ 评估规则:                             │
│  ☑ 缺陷密度                 [AND]     │
│    • Normal: < 10 d/mm²              │
│    • Warning: 10-20 d/mm²            │
│    • Critical: > 20 d/mm²            │
│                                      │
│  ☑ Die 位置                 [AND]     │
│    • 允许值: Core / Periphery / Edge │
│                                      │
│  ☑ 关键层标记               [AND]     │
│                                      │
└──────────────────────────────────────┘
```

### 2.3 Dashboard 扩展（第 13 节延伸）

在数据集质量评估中新增指标：

- **时间约束遵守率**：多少百分比的节点有 SLA 定义
- **规则完整度**：多少百分比的决策节点有详细规则定义
- **临界路径识别**：自动识别硬性 deadline 形成的关键路径

---

## 数据迁移策略

### 现有数据的升级

对于已采集的工作流（仅包含 `expected_duration` 和 `decision_criteria` 的记录）：

1. **保持不动**：旧数据仍然有效，UI 兼容显示
2. **标记为"待升级"**：Dashboard 可显示哪些记录还没升级到新 Schema
3. **渐进升级**：在专家修改流程时，AI 可主动询问并补全新信息

示例：

```
AI: "我注意到这个'初评'节点，有没有时间上的约束？比如多久内要完成？"
专家: "两个小时内要出结果"
AI: [生成 sla_config] 
```

---

## Validator 规则更新

在 Graph Validator（PRD 第 3.4 节）中新增检查：

### 新增检查项

1. **SLA 逻辑检查**
   - `from_trigger` 不能指向不存在的节点
   - `violation_action` 与 `enforced` 的逻辑一致性

2. **评估规则检查**
   - `evaluation_criteria[].id` 必须唯一（同一节点内）
   - 若 `logic="AND"`，下一个条件必须存在
   - `depends_on` 不能形成循环依赖

3. **临界路径检查**（可选，用于后续分析）
   - 标记所有 `enforced=true` 且 `type="deadline"` 的节点
   - 识别这些节点之间是否形成串联的关键路径

---

## LLM 采集提示词调整

在会话采集阶段（第 4 节采集问题阶段），AI 应在适当时机主动询问：

### P6（规则经验阶段）之后，新增 P6.5（时间约束询问）

提示词示例：

```
关于「{节点名称}」这一步，让我确认一下时间要求：
1. 有没有完成的时间限制？如果有，多长时间？
2. 这个时间限制是硬性的还是目标值？
3. 如果超期了会怎样处理？

例如："初评通常要在两小时内完成，超期就要向经理报告"
```

在前述基础上，如果是决策节点，进一步询问：

```
初评需要检查哪些指标或条件？每个的标准是什么？
例如："要看缺陷密度（每平方毫米少于10个算正常），还要看落在哪个die..."
```

---

## 文件清单

### 已修改

- `docs/expert-workflow-collection/schema/workflow_graph_schema_v2.json`
  - 添加 `sla_config` 对象定义
  - 添加 `evaluation_criterion` 对象定义
  - 在 node 中添加 `sla_config` 和 `evaluation_criteria` 字段

- `docs/expert-workflow-collection/schema/workflow_graph_v2_sample.json`
  - 在"试产并首件检验"节点（n9）演示新字段的使用

### 后续待创建

- UI 层：React 组件展示 SLA 标签和评估规则详情面板（第 11.4 节实现）
- Validator 扩展：新增 SLA 和规则逻辑检查（graph_ops.py 和 validator 模块）
- LLM Prompt：采集阶段的新询问逻辑（guide_service.py）
- Dashboard 扩展：时间约束遵守率、规则完整度指标（第 13 节扩展）

---

## 工作量估算

| 部分 | 工作量 | 优先级 |
|---|---|---|
| Schema 更新（已完成） | 1-2h | P0 |
| 样例数据（已完成） | 1h | P0 |
| 本文档（已完成） | 2-3h | P0 |
| **小计 Phase 1** | **4-6h** | |
| UI 可视化（节点标签+详情面板） | 3-4h | P1 |
| Validator 规则更新 | 2-3h | P1 |
| LLM Prompt 调整 | 2-3h | P1 |
| Dashboard 扩展 | 3-4h | P2 |
| 数据迁移脚本 | 2-3h | P2 |
| **小计 Phase 2** | **12-17h** | |

---

## FAQ

### Q: 为什么保留旧字段而不直接替换？

**A**: 出于向后兼容考虑。已采集的几十个工作流记录使用旧格式，直接删除会破坏这些数据。新系统优先使用新字段，但能自动降级处理旧字段。

### Q: `sla_config.duration` 为什么同时支持 ISO 8601 和自然语言？

**A**: 前者（PT2H）便于机器处理和转换；后者（2h）更符合采集时的自然表达。存储时统一为 ISO 8601，显示时转回自然语言。

### Q: 如果一个节点既有硬性 deadline 又有目标时长，怎么表示？

**A**: 建议分两个节点：一个是"必须完成"（deadline），下一个是"做得更好"（target）。或者在 description 中说明"目标2小时，必须不超过4小时"。

### Q: evaluation_criteria 与 rules 的区别是什么？

**A**: 
- `evaluation_criteria`：该节点内部的决策标准或评估项（"缺陷密度"是什么、怎么测）
- `rules`：适用于多个节点的跨流程规则（"连续3件超差应通知质量工程师"）

一个节点既可以有 `evaluation_criteria`（局部决策规则），也可以关联 `rule_ids`（全局 SOP 规则）。

---

## 相关链接

- PRD 第 3.3/3.4 节：Graph Validator 规则
- PRD 第 4 节：采集问题阶段和优先级
- PRD 第 11 节：DAG 可视化设计
- PRD 第 13 节：Dashboard 设计
- PRD 第 15 节：LLM 使用清单
