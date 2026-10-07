# Phase 3-A Schema 扩展示例

本文档展示如何使用 Phase 3-A 中新增的 Schema 维度。

## 目录

1. [聚合和趋势条件](#聚合和趋势条件)
2. [权限分级和多层签字](#权限分级和多层签字)
3. [临时措施生命周期](#临时措施生命周期)
4. [多维追溯和隔离](#多维追溯和隔离)

---

## 聚合和趋势条件

### 场景：温度趋势判断

在某些测试过程中，不仅需要判断单个数据点是否超过阈值，还需要判断一段时间内的趋势。

**示例**：半导体测试中，设备温度持续上升可能预示故障，需要提前采取行动。

```json
{
  "node_id": "n_temperature_check",
  "node_type": "decision",
  "label": "检查设备温度趋势",
  "decision_question": "设备温度是否持续上升？",
  "evaluation_criteria": [
    {
      "id": "temperature_trend",
      "name": "设备温度趋势",
      "type": "metric",
      "unit": "°C",
      "thresholds": {
        "normal": "< 40",
        "warning": "40-50",
        "critical": "> 50"
      },
      "aggregation": {
        "method": "trend",
        "window_size": 7,
        "operator": "all_increasing",
        "threshold": "3°C",
        "min_samples": 5,
        "description": "过去 7 个测量点持续上升，每次上升超过 3°C"
      }
    }
  ]
}
```

### 场景：连续超差判断

**示例**：质量检验中，连续两个产品都超过公差范围。

```json
{
  "node_id": "n_defect_check",
  "node_type": "decision",
  "label": "检查缺陷模式",
  "decision_question": "是否连续出现超差？",
  "evaluation_criteria": [
    {
      "id": "defect_pattern",
      "name": "缺陷连续性",
      "type": "metric",
      "unit": "个",
      "aggregation": {
        "method": "pattern",
        "window_size": 5,
        "operator": "two_exceeding",
        "threshold": "1",
        "min_samples": 2,
        "description": "过去 5 个产品中，连续 2 个或以上超差"
      }
    }
  ]
}
```

---

## 权限分级和多层签字

### 场景：产品 Release 的多角色批准

在制造行业中，产品 release 通常需要多个不同角色的批准，且这些批准可能有不同的顺序和条件。

**示例**：产品 release 需要设备工程师、工艺工程师、质量工程师三个角色的批准。

```json
{
  "node_id": "n_release_decision",
  "node_type": "approval",
  "label": "产品 Release 批准",
  "actor_roles": ["设备工程师", "工艺工程师", "质量工程师"],
  "approval_matrix": [
    {
      "approval_type": "equipment_release",
      "required_roles": ["设备工程师"],
      "sequence": "sequential",
      "criteria": "设备状态正常，无报警和故障记录",
      "escalation_level": 1
    },
    {
      "approval_type": "process_release",
      "required_roles": ["工艺工程师"],
      "sequence": "sequential",
      "criteria": "工艺参数在规定范围内，刀具寿命充足",
      "escalation_level": 1
    },
    {
      "approval_type": "quality_release",
      "required_roles": ["质量工程师"],
      "sequence": "sequential",
      "criteria": "首件检验合格，性能指标符合要求",
      "escalation_level": 2
    }
  ],
  "description": "需要三个部门的顺序批准；如质量工程师拒绝，升级到生产主管"
}
```

### 场景：并行批准

**示例**：某些决策允许多个角色并行审批（如并行的工艺和质量检查）。

```json
{
  "node_id": "n_parallel_release",
  "node_type": "approval",
  "label": "工艺和质量并行批准",
  "approval_matrix": [
    {
      "approval_type": "process_and_quality_release",
      "required_roles": ["工艺工程师", "质量工程师"],
      "sequence": "parallel",
      "criteria": "工艺和质量两个方面都确认无问题"
    }
  ]
}
```

---

## 临时措施生命周期

### 场景：临时 Bypass 措施

在排故过程中，有时需要采取临时措施（如临时 bypass 某个检验或工艺步骤），但这些措施有明确的有效期。

**示例**：设备故障期间，临时 bypass 某个测试，但只允许使用 3 个 lot 或 72 小时。

```json
{
  "node_id": "n_equipment_fault_recovery",
  "node_type": "activity",
  "label": "临时 Bypass 测试",
  "actor_roles": ["设备工程师", "质量工程师"],
  "retry_semantics": {
    "enabled": true,
    "is_temporary": true,
    "max_retries_per_phase": 1,
    "expiration": {
      "duration": "PT72H",
      "lot_count": 3,
      "expiration_trigger": "duration_or_count",
      "description": "72 小时或 3 个 lot 后自动失效，先达到任一条件则失效"
    },
    "revocation_trigger": {
      "type": "reoccurrence",
      "days": 30,
      "description": "如果 30 天内同一故障再次出现，此临时措施立即失效并需要正式的长期解决方案"
    }
  },
  "description": "这是一个临时措施，只在设备故障排除期间使用"
}
```

### 场景：临时工艺变更

**示例**：工艺参数的临时调整（如降低检测强度以加快生产速度）。

```json
{
  "node_id": "n_temp_process_change",
  "node_type": "activity",
  "label": "临时降低检测强度",
  "retry_semantics": {
    "is_temporary": true,
    "expiration": {
      "duration": "PT168H",
      "lot_count": 10,
      "expiration_trigger": "duration_and_count",
      "description": "既需要满足 168 小时 AND 10 个 lot 两个条件才失效"
    },
    "escalation_on_repeat": {
      "enabled": true,
      "trigger": "same_condition",
      "action": "create_capa",
      "description": "如果再次因相同原因采取此临时措施，则触发 CAPA 流程进行长期改进"
    }
  }
}
```

---

## 多维追溯和隔离

### 场景：设备故障导致的产品隔离

当某台设备发现问题时，需要隔离所有在此设备上加工的产品。

**示例**：

```json
{
  "node_id": "n_equipment_issue_found",
  "node_type": "event",
  "label": "发现设备故障",
  "containment_scope": {
    "dimension": "equipment_id",
    "rule": "all_products_on_same_equipment",
    "applicable_conditions": ["设备故障类型为机械故障", "故障发生后未修复"]
  }
}
```

对应的边：

```json
{
  "edge_id": "e_equipment_issue_to_hold",
  "from": "n_equipment_issue_found",
  "to": "n_equipment_release_hold",
  "edge_type": "exception_forward",
  "label": "设备故障",
  "containment_scope": {
    "dimension": "equipment_id",
    "rule": "hold_all_products_on_this_equipment"
  }
}
```

### 场景：物料批次问题

**示例**：某批物料发现质量问题，需要隔离此批次的所有产品。

```json
{
  "containment_scope": {
    "dimension": "material_id",
    "rule": "all_products_with_same_material_batch",
    "applicable_conditions": ["物料来自同一批次", "物料测试结果不合格"]
  }
}
```

### 场景：多维隔离规则

对于某些复杂情况，可能需要按多个维度进行追溯和隔离。

**示例**：

```json
{
  "node_id": "n_complex_issue_analysis",
  "node_type": "activity",
  "label": "复杂问题根因分析",
  "description": "根据根因确定隔离维度",
  "containment_scope": {
    "dimension": "lot_id",
    "rule": "all_products_in_same_lot",
    "applicable_conditions": [
      "根因为工艺参数不稳定",
      "影响范围仅限于单个 lot"
    ]
  }
}
```

---

## 完整示例：综合应用

以下是一个综合应用了多个 Phase 3-A 维度的工作流片段：

```json
{
  "node_id": "n_qa_initial_assessment",
  "node_type": "approval",
  "label": "初评阶段 - 多维决策",
  "decision_question": "产品是否通过初评？",
  "sla_config": {
    "type": "deadline",
    "duration": "PT2H",
    "from_trigger": "previous_node_completed",
    "enforced": true,
    "violation_action": "escalate"
  },
  "evaluation_criteria": [
    {
      "id": "dimensional_accuracy",
      "name": "尺寸精度",
      "type": "metric",
      "unit": "μm",
      "thresholds": {
        "normal": "< 10",
        "warning": "10-20",
        "critical": "> 20"
      },
      "aggregation": {
        "method": "trend",
        "window_size": 5,
        "operator": "all_increasing",
        "description": "过去 5 个产品尺寸误差持续增大"
      }
    },
    {
      "id": "surface_finish",
      "name": "表面粗糙度",
      "type": "metric",
      "unit": "Ra μm",
      "thresholds": {
        "normal": "< 1.6",
        "warning": "1.6-3.2",
        "critical": "> 3.2"
      },
      "logic": "OR"
    }
  ],
  "approval_matrix": [
    {
      "approval_type": "quality_initial_approval",
      "required_roles": ["质量工程师"],
      "sequence": "sequential",
      "criteria": "尺寸和表面粗糙度都在正常范围"
    },
    {
      "approval_type": "process_initial_approval",
      "required_roles": ["工艺工程师"],
      "sequence": "sequential",
      "criteria": "工艺参数符合规范"
    }
  ],
  "retry_semantics": {
    "enabled": true,
    "is_temporary": false,
    "max_retries_per_phase": 2
  }
}
```

---

## 向后兼容性

所有 Phase 3-A 新增字段都是**可选的**，不存在时系统应按照 Phase 1/2 的方式处理：

- 如果没有 `aggregation`，仅使用单点的 `thresholds`
- 如果没有 `approval_matrix`，仅使用 `actor_roles` 和 `decision_criteria`
- 如果 `retry_semantics` 中没有 `is_temporary`，按常规重试处理
- 如果没有 `containment_scope`，按全局默认隔离规则处理

---

## 采集指导

### 采集问题示例

对于 `aggregation`：
- "决策条件是单点阈值还是需要看趋势？"
- "如果是趋势判断，关注哪些特征？（上升/下降/方差/周期等）"
- "需要多少个历史数据点？"

对于 `approval_matrix`：
- "这个决策需要哪些角色的批准？"
- "这些批准是顺序的还是并行的？"
- "如果某个角色拒绝，会升级到谁？"

对于 `expiration`：
- "这个措施是临时的吗？有效期是多长？"
- "是按时间、产品数量、还是两者都算？"
- "多久后失效条件会被触发？"

对于 `containment_scope`：
- "如果发现问题，影响范围是什么？"
- "按什么维度进行追溯和隔离？"
- "不同的根因会导致不同的隔离范围吗？"

---

**文档版本**：1.0  
**最后更新**：2026-10-07  
**适用 Schema 版本**：v2.0（Phase 3-A 扩展）
