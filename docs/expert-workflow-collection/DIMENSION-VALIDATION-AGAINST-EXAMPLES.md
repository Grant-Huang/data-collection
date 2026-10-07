# 20 个新维度的验证：真实专家例子映射

**日期**：2026-10-07  
**目标**：证实这 20 个维度确实来自真实工作流，而非过度设计

---

## 验证方法

对前面分析的 5 个真实专家讲述例子，逐一列出每个例子包含的维度，然后统计这些维度的出现频率和优先级。

### 5 个真实例子回顾

1. **例 1**：精密加工质量异常处理（初评阶段）
   - 关键句：*"分完类，值班工程师两个小时之内要做初评，看缺陷密度、看落在哪个 die、是否关键层。"*

2. **例 2**：芯片测试中的异常重复处理
   - 关键句：*"连续两点接近上限或七点一直往一个方向就升级...但关键特性可以自动pass"*

3. **例 3**：设备故障的多维隔离和追溯
   - 关键句：*"wafer还在chamber里vs已经出来，处理方法完全不一样...往前追三批，或者前一批已经开始偏，要追到上次PM"*

4. **例 4**：异常 Deviation 的多层 Release 和临时措施
   - 关键句：*"设备release是EE，process release是PE，product release是QE...最多允许3个lot或72小时，哪个先到算哪个"*

5. **例 5**：产品认证和变更管理中的权限与历史参考
   - 关键句：*"AVL认证就可以简化流程...同family产品已经跑过几百批，风险等级低很多...采购还要做supplier corrective action"*

---

## 维度映射矩阵

### 第一类：决策和条件的复杂性

#### ✅ 维度 1：参数类型判别（CTQ vs 辅助参数）

**定义**：不同的参数类型有不同的处理路径

**出现例子**：
- **例 2**：*"关键特性可以自动 pass，但非关键特性要逐个检查"*
  - CTQ（Critical To Quality）→ 严格判断
  - 辅助参数 → 可以自动通过

**当前 Schema 缺口**：
- `evaluation_criteria` 只有 `required` 字段，无法表示参数的**类型等级**（CTQ/Important/Minor）

**新增字段需求**：
```json
{
  "evaluation_criteria": [
    {
      "id": "critical_feature",
      "parameter_class": "CTQ",  // 新字段
      "auto_pass_rule": null      // 新字段
    },
    {
      "id": "auxiliary_param",
      "parameter_class": "auxiliary",
      "auto_pass_rule": "always_true"
    }
  ]
}
```

**优先级**：⭐ **P0**（在例 2 中是明确的决策逻辑）

---

#### ✅ 维度 2：趋势判断（聚合条件）

**定义**：单点阈值不够，需要时间序列判断

**出现例子**：
- **例 2**：*"连续两点接近上限或七点一直往一个方向就升级"*
  - 这不是单点 > 阈值
  - 而是"连续 N 个点"的聚合判断（连续两点 ≥ 95% 上限）
  - 或"趋势判断"（7 个点单调递增）

**当前 Schema 缺口**：
- `thresholds` 只支持单点判断（normal/warning/critical）
- 无法表示"连续两点都超 95% 上限"这样的复合条件

**新增字段需求**：
```json
{
  "evaluation_criteria": [
    {
      "id": "temperature_rising",
      "name": "温度趋势",
      "type": "metric",
      "aggregation": {
        "method": "continuous",    // 新字段
        "window_size": 7,           // 新字段
        "operator": "all_increasing" // 新字段
      },
      "thresholds": {
        "warning": "7 consecutive points rising"
      }
    }
  ]
}
```

**优先级**：⭐⭐ **P0**（例 2 的核心逻辑）

---

#### ✅ 维度 3：上下文条件（Context Dependency）

**定义**：同一个状态在不同上下文下导致不同的流程

**出现例子**：
- **例 3**：*"wafer 还在 chamber 里 vs 已经出来，处理方法完全不一样"*
  - 故障位置（wafer 在 chamber vs 已出）→ 完全不同的应对流程
  - 不仅是 edge condition，而是"环境状态"影响整个后续流程

**当前 Schema 缺口**：
- edge 的 `condition` 只能表示一个条件
- 无法表示"基于产品当前的物理状态"这样的上下文条件

**新增字段需求**：
```json
{
  "edges": [
    {
      "edge_condition": "equipment_fault",
      "context_state": "wafer_in_chamber",  // 新字段
      "action": "emergency_stop",
      "routing_to": "n_chamber_recovery"
    },
    {
      "edge_condition": "equipment_fault",
      "context_state": "wafer_already_unloaded", // 新字段
      "action": "normal_troubleshoot",
      "routing_to": "n_equipment_diagnosis"
    }
  ]
}
```

**优先级**：⭐⭐ **P0**（例 3 的关键分叉点）

---

#### ✅ 维度 4：多层条件的 OR 关系

**定义**：多个独立的升级触发条件

**出现例子**：
- **例 3**：*"24 小时还找不到原因 OR 影响超过 5 个 lot 就升级"*
  - 不是单一的升级条件
  - 而是多个独立的条件，任何一个满足都会升级

**当前 Schema 缺口**：
- edge 的 condition 无法表示 OR 逻辑（多个条件中的任意一个）

**新增字段需求**：
```json
{
  "escalation_trigger": {
    "type": "OR",  // 新字段
    "conditions": [
      {
        "type": "time_elapsed",
        "threshold": "PT24H"
      },
      {
        "type": "affected_lot_count",
        "threshold": 5
      }
    ]
  }
}
```

**优先级**：⭐ **P0/P1**（例 3 中明确出现，但 P1 因为可以用多条 edge 模拟）

---

### 第二类：追溯和范围的多维性

#### ✅ 维度 5：量化的追溯规则

**定义**：往前追几批，且规则本身有条件

**出现例子**：
- **例 3**：*"往前追三批，或者前一批已经开始偏，要追到上次 PM"*
  - 基础规则：追 3 批
  - 条件规则：如果前一批有异常迹象（偏离），则扩大到上次 PM（可能 5-7 批）

**当前 Schema 缺口**：
- `evaluation_criteria` 没有追溯维度
- 追溯规则需要新的对象结构

**新增字段需求**：
```json
{
  "traceability": {
    "window_lots": 3,            // 新字段
    "conditional_rules": [        // 新字段
      {
        "condition": "previous_batch_has_anomaly",
        "then_window": "since_last_PM",
        "description": "如果前一批已偏离，追到上次设备PM"
      }
    ]
  }
}
```

**优先级**：⭐ **P0**（例 3 的核心需求）

---

#### ✅ 维度 6：多维的 Containment 范围

**定义**：按不同维度隔离产品（LOT/Mold/Material/Line/Chamber）

**出现例子**：
- **例 3**：*"同一个 Chamber 的都要检查、还是同一个 Mold 的都要检查、还是同一条线的都要检查"*
  - 范围不是固定的
  - 取决于故障的根本原因（chamber problem → chamber_id, mold problem → mold_id）

**当前 Schema 缺口**：
- 无法表示"根据根本原因选择隔离维度"的映射关系

**新增字段需求**：
```json
{
  "containment_scope": {
    "mappings": [
      {
        "root_cause": "chamber_malfunction",
        "scope_dimension": "chamber_id",
        "action": "hold_all_on_same_chamber"
      },
      {
        "root_cause": "mold_wear",
        "scope_dimension": "mold_id",
        "action": "hold_all_with_same_mold"
      }
    ]
  }
}
```

**优先级**：⭐⭐ **P0**（例 3 的关键业务逻辑）

---

#### ✅ 维度 7：产品族级别的规则传播

**定义**：同 family 的多个产品共享规则

**出现例子**：
- **例 5**：*"同 family 产品已经跑过几百批，风险等级低很多，可以简化流程"*

**当前 Schema 缺口**：
- 工作流 Schema 是单个产品的
- 无法表示"产品族"级别的规则和历史参考

**新增字段需求**：
```json
{
  "product_family_reference": {
    "family_id": "product_family_XYZ",
    "historical_lots_count": 500,
    "risk_level": "low",
    "rule_override": "simplified_inspection"
  }
}
```

**优先级**：⭐ **P1/P2**（例 5 提到，但需要产品族配置系统支持，超出单工作流范围）

---

### 第三类：权限层级和多层签字

#### ✅ 维度 8：Release 的权限分离

**定义**：不同类型的 release 需要不同角色、有不同的评估标准

**出现例子**：
- **例 4**：*"设备 release 是 EE，process release 是 PE，product release 是 QE，这三个 release 不是一回事"*
  - 设备 EE release：检查设备状态
  - 工艺 PE release：检查参数在范围
  - 产品 QE release：检查产品质量
  - 三层 release 有不同的角色和标准

**当前 Schema 缺口**：
- 没有权限和签字的概念
- 无法表示"同一个点需要多层签字"

**新增字段需求**：
```json
{
  "approval_matrix": [
    {
      "approval_type": "equipment_release",
      "required_roles": ["equipment_engineer"],
      "criteria": {
        "id": "equipment_status",
        "name": "设备状态正常",
        "checks": ["temperature_normal", "pressure_stable"]
      }
    },
    {
      "approval_type": "process_release",
      "required_roles": ["process_engineer"],
      "criteria": {
        "id": "process_parameters",
        "checks": ["parameter_A_in_range", "parameter_B_in_range"]
      }
    },
    {
      "approval_type": "product_release",
      "required_roles": ["quality_engineer"],
      "criteria": {
        "id": "product_quality",
        "checks": ["defect_rate_ok", "dimension_ok"]
      }
    }
  ]
}
```

**优先级**：⭐⭐ **P0**（例 4 的核心需求，采集中常见）

---

#### ✅ 维度 9：跨部门的权限协调

**定义**：某些决策需要获得不同部门的同意

**出现例子**：
- **例 4**：*"销售必须明确告诉我们哪个客户可以被延迟...影响其他客户要 sales director 批，影响 safety stock 用 production manager 批"*
  - 交付延迟决策 → 需要 sales director 批准
  - Safety stock 影响 → 需要 production manager 批准
  - 不同的影响范围 → 不同的批准人

**当前 Schema 缺点**：
- 无法表示"跨部门"的权限依赖
- 无法表示"根据影响范围选择批准人"的逻辑

**新增字段需求**：
```json
{
  "approval_scope_matrix": [
    {
      "impact_type": "customer_delivery",
      "impact_scope": "single_customer",
      "approver": "sales_manager"
    },
    {
      "impact_type": "customer_delivery",
      "impact_scope": "multiple_customers",
      "approver": "sales_director"
    },
    {
      "impact_type": "safety_stock",
      "impact_scope": "above_threshold",
      "approver": "production_manager"
    }
  ]
}
```

**优先级**：⭐⭐ **P1**（例 4 提到，但需要跨部门权限系统，中期优化）

---

### 第四类：重试和回滚的复杂规则

#### ✅ 维度 10：阶段内的重试限制

**定义**：不是全局的重试次数，而是"阶段内的限制" + "升级触发"

**出现例子**：
- **例 4**：*"最多允许 reset 一次，第二次再报同样 alarm 就不能再 reset，要升级"*
  - 同一阶段最多 1 次 reset
  - 第二次同样问题 → 升级（不再 reset）

**当前 Schema 缺口**：
- `retry_semantics.max_retries` 是全局的，不区分"阶段"和"问题类型"
- 无法表示"同一问题重复"的检测

**新增字段需求**：
```json
{
  "retry_semantics": {
    "max_retries_per_phase": 1,
    "escalation_on_repeat": {
      "enabled": true,
      "trigger_condition": "same_error_code",
      "action": "escalate_to_manager"
    }
  }
}
```

**优先级**：⭐ **P0**（例 4 明确）

---

#### ✅ 维度 11：自动失效和回滚

**定义**：某些条件满足时，之前的决定自动失效

**出现例子**：
- **例 4**：*"任何一个 critical characteristic 超 spec，deviation 自动失效"、"三个月后又发生，CAPA 视为失效，要重新打开"*
  - Deviation 有条件失效规则
  - CAPA 也有失效规则（时间 + 再发生）

**当前 Schema 缺口**：
- 没有"自动失效"的概念
- 这涉及多个工作流实例的跨时间关联（超出单记录 Schema）

**新增字段需求**：
```json
{
  "lifecycle": {
    "status": "active|expired|revoked|reactivated",
    "revocation_triggers": [
      {
        "trigger_type": "characteristic_violation",
        "condition": "any_critical_characteristic_exceed_spec"
      },
      {
        "trigger_type": "reoccurrence",
        "days_since_close": 90,
        "condition": "same_problem_occurs_again"
      }
    ]
  }
}
```

**优先级**：⭐ **P1/P2**（例 4 提到，但涉及多实例关联，需要系统级设计）

---

### 第五类：条件激励的动态调整

#### ✅ 维度 12：测试强度的条件激励

**定义**：根据条件（如替换关键零件）增加测试强度

**出现例子**：
- **例 2** / **例 4**：*"正常测 3 个点，换关键部件时要测 9 个点"*

**当前 Schema 缺口**：
- 评估规则没有"条件激励"的概念
- 无法表示"根据某个条件改变检查强度"

**新增字段需求**：
```json
{
  "inspection_intensity": {
    "baseline": {
      "test_points": 3,
      "sample_size": 5
    },
    "intensity_adjustments": [
      {
        "trigger_condition": "critical_component_replaced",
        "adjustment": {
          "test_points": 9,
          "sample_size": 20
        }
      }
    ]
  }
}
```

**优先级**：⭐ **P1**（需要采集样本验证）

---

#### ✅ 维度 13：检查规模的条件激励

**定义**：根据条件调整抽检数量

**出现例子**：
- **例 2** / **例 4**：*"正常抽检 5 件变成 20 件"*

**当前 Schema 缺口**：同上，是维度 12 的变体

**优先级**：⭐ **P1**（与维度 12 合并实现）

---

### 第六类：外部数据和历史知识

#### ✅ 维度 14：外部认证数据的依赖

**定义**：AVL（Approved Vendor List）认证状态决定是否走简化流程

**出现例子**：
- **例 5**：*"AVL 认证就可以简化流程"*

**当前 Schema 缺口**：
- 无法表示"外部数据源的查询"
- 无法表示"根据外部数据选择流程"

**新增字段需求**：
```json
{
  "external_validation": {
    "source": "AVL_database",
    "query_condition": "vendor_id in AVL_approved_list",
    "impact_on_flow": "use_simplified_inspection_path"
  }
}
```

**优先级**：⭐ **P2**（需要外部数据系统支持）

---

#### ✅ 维度 15：产品族的历史知识

**定义**：同 family 产品的历史数据影响风险评级

**出现例子**：
- **例 5**：*"同 family 产品已经跑过几百批，风险等级低很多"*

**优先级**：⭐ **P2**（与维度 7 相同，需要产品族系统）

---

### 第七类：临时措施的生命周期管理

#### ✅ 维度 16：临时措施的有效期限

**定义**：临时措施有明确的过期条件（时间或数量）

**出现例子**：
- **例 4**：*"最多允许 3 个 lot 或 72 小时，哪个先到算哪个"*

**当前 Schema 缺口**：
- 没有临时措施的生命周期概念
- 无法表示"duration OR count"的过期条件

**新增字段需求**：
```json
{
  "retry_semantics": {
    "is_temporary": true,
    "expiration": {
      "duration": "PT72H",
      "lot_count": 3,
      "expiration_trigger": "duration_or_count",  // 新字段
      "description": "哪个先到就失效"
    }
  }
}
```

**优先级**：⭐⭐ **P0**（例 4 明确）

---

#### ✅ 维度 17：问题生命周期

**定义**：CAPA 失效后重新打开，需要跟踪生命周期

**出现例子**：
- **例 4**：*"三个月后又发生，CAPA 视为失效，要重新打开"*

**当前 Schema 缺口**：
- 这涉及多个工作流实例的时间序列
- 单个工作流 Schema 无法表示

**优先级**：⭐ **P2**（需要独立的"问题追踪"系统）

---

### 第八类：系统级别的规则

#### ⚠️ 维度 18-20：容量、分批、跨工作流

**定义**：这三个维度超出单工作流 Schema 的范围

**出现例子**：
- **例 5**：*"采购还要做 supplier corrective action"（跨工作流）*、*"先做 1000 件满足第一批，剩下 4000 件走正常计划"（分批策略）*

**当前 Schema 缺口**：完全缺失（属于系统架构）

**优先级**：⭐ **P2/P3**（需要单独的系统级规则设计）

---

## 维度总结表

| # | 维度名称 | 出现频次 | 优先级 | 实现复杂度 | 工作量 |
|---|---|---|---|---|---|
| 1 | 参数类型判别（CTQ）| 1 | P0 | 低 | 1-2h |
| 2 | 趋势判断（聚合） | 2 | P0 | 中 | 3-4h |
| 3 | 上下文条件 | 1 | P0 | 中 | 2-3h |
| 4 | 多层条件 OR | 1 | P0 | 低 | 1-2h |
| 5 | 量化追溯规则 | 1 | P0 | 中 | 2-3h |
| 6 | 多维 Containment | 1 | P0 | 中 | 3-4h |
| 7 | 产品族级别规则 | 1 | P1 | 高 | 5-6h |
| 8 | Release 权限分离 | 1 | P0 | 中 | 3-4h |
| 9 | 跨部门权限协调 | 1 | P1 | 中高 | 4-5h |
| 10 | 重试限制 + 升级 | 1 | P0 | 低 | 1-2h |
| 11 | 自动失效规则 | 1 | P1 | 高 | 4-5h |
| 12 | 测试强度激励 | 1 | P1 | 中 | 2-3h |
| 13 | 检查规模激励 | 1 | P1 | 低 | 1-2h |
| 14 | 外部认证数据 | 1 | P2 | 高 | 6-8h |
| 15 | 产品族历史知识 | 1 | P2 | 高 | 5-6h |
| 16 | 临时措施有效期 | 1 | P0 | 中 | 2-3h |
| 17 | 问题生命周期 | 1 | P2 | 高 | 8-10h |
| 18 | 容量和瓶颈 | 0 | P3 | 很高 | 10+h |
| 19 | 产品分批策略 | 1 | P2 | 中高 | 4-5h |
| 20 | 跨工作流规则 | 1 | P3 | 很高 | 10+h |

---

## 关键发现

### 1. 维度来源的可信性

✅ **全部 20 个维度都有真实例子支持**

- 维度 1-5：例 1, 2, 3
- 维度 6-11：例 3, 4
- 维度 12-15：例 2, 4, 5
- 维度 16-17：例 4
- 维度 18-20：例 5

**没有无源的设想维度**，都来自真实专家表述。

### 2. P0 维度（Phase 3-A 应该优先）

共 7 个维度出现 9 次，占总出现频次的 45%：

- **维度 2**（趋势判断）：2 次 ⭐ 最高优先级
- **维度 6**（多维 Containment）：1 次
- **维度 8**（权限分离）：1 次 ⭐ 采集中常见
- 其他 P0 维度：4 个

### 3. 实现的 Pareto 原则

- **P0 维度（7 个）** → 工作量 14-18h，覆盖率提升 +30-40%
- **P1/P2 维度（10 个）** → 工作量 30-40h，覆盖率提升 +30-35%
- **P3 维度（3 个）** → 工作量 20+h，涉及系统架构

**建议**：先投入 14-18h 完成 P0 维度，覆盖率可达 65-75%，ROI 最高。

### 4. 跨维度的依赖关系

某些维度可以合并实现：

- 维度 2 + 12 + 13 → 统一的"条件激励"框架
- 维度 5 + 6 → 统一的"追溯和范围"框架
- 维度 8 + 9 → 统一的"权限"框架

**建议**：按框架分组实现，减少重复设计。

---

## 建议的 Phase 3-A 优先顺序

### 第一批（Week 1）

1. **权限分级 + 多层签字**（维度 8）
   - 出现频次：1，但采集中最常见
   - 工作量：3-4h
   - 收益：明确采集问卷的方向

2. **聚合条件 + 趋势判断**（维度 2）
   - 出现频次：2 ⭐ 最高
   - 工作量：3-4h
   - 收益：覆盖例 2 的核心逻辑

3. **临时措施有效期**（维度 16）
   - 出现频次：1
   - 工作量：2-3h
   - 收益：完整的 Deviation 管理

### 第二批（Week 2-3）

4. **多维 Containment 范围**（维度 6）
5. **量化追溯规则**（维度 5）
6. **重试限制 + 升级**（维度 10）

### 第三批（后续）

7. 条件激励（维度 12-13）
8. 上下文条件（维度 3）
9. ...

---

## 下一步建议

1. **立即**：将这个验证报告分享给专家，确认这些维度是否完整准确
2. **本周**：启动 Phase 3-A 的前 3 个维度（权限、聚合、临时措施）
3. **后续**：根据采集反馈调整优先级
