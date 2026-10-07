# Phase 3 战略规划：应对 35-40% 覆盖率缺口

**日期**：2026-10-07  
**状态**：规划中  
**目标**：将覆盖率从 35-40% 提升至 75%+（可实现的范围）

---

## 执行摘要

### 现状评估

前面的分析发现了 **20 个新信息维度**，当前 Schema 仅能覆盖 35-40%：

| 层级 | 覆盖率 | 原因 | 示例 |
|---|---|---|---|
| **第一层（已覆盖）** | 95% ✅ | 单节点时间 + 基础评估规则 | SLA 类型、阈值 |
| **第二层（可覆盖）** | 20-30% ⚠️ | 多节点流程、条件复杂性 | 聚合条件、权限矩阵 |
| **第三层（系统级）** | 0% ❌ | 超出单记录范围 | 容量规划、跨工作流规则 |

### 三阶段策略

```
Phase 1/2 ✅ 完成（Schema + UI 原型）
    ↓
Phase 3-A 🎯 优先（+30-40% 覆盖率，可在现有框架内实现）
    ├─ 聚合和趋势条件
    ├─ 权限分级 + 签字流程
    ├─ 临时措施生命周期
    ├─ 简化的多维范围
    └─ 工作量：8-12h
    ↓
Phase 3-B 📋 后续（系统架构，单独规划）
    ├─ 外部数据依赖体系
    ├─ 完整的问题生命周期管理
    ├─ 容量规划和瓶颈管理
    └─ 跨工作流规则引擎
```

---

## 维度优先级评估矩阵

### 评估标准

- **可实现性**：能否在当前 Schema 框架内实现？
- **业务价值**：对真实工作流采集的帮助有多大？
- **工作量**：实现所需的时间成本
- **依赖关系**：是否依赖其他维度或系统?

### 20 个维度的分类

#### 🎯 P0（Phase 3-A 优先实现）

这些维度可以通过 Schema 扩展 + UI 改进直接实现，且对采集工作有重大帮助。

**1. 聚合和趋势条件** ⭐ 最高优先级
- **定义**：单点阈值不够，需要时间序列判断（"连续两点接近上限"、"七点一直往一个方向"）
- **实现方式**：在 `evaluation_criteria` 中新增可选字段
  ```json
  {
    "id": "temperature_trend",
    "name": "温度趋势",
    "type": "metric",
    "aggregation": {
      "method": "trend|pattern|continuous",
      "window_size": 7,
      "operator": "all_increasing|two_exceeding|variance_above"
    }
  }
  ```
- **业务价值**：高（质量监控的常见模式）
- **工作量**：3-4h（Schema 设计 + UI 展示 + 计算逻辑）
- **覆盖率提升**：+8-10%

**2. 权限分级和多层签字**
- **定义**：不同类型的 release 需要不同角色的批准（设备 EE / 工艺 PE / 产品 QE）
- **实现方式**：新增 `approval_matrix` 字段
  ```json
  {
    "node_id": "release_decision",
    "approval_matrix": [
      {
        "approval_type": "equipment_release",
        "required_roles": ["equipment_engineer"],
        "criteria": "设备状态正常"
      },
      {
        "approval_type": "process_release",
        "required_roles": ["process_engineer"],
        "criteria": "工艺参数在范围内"
      }
    ]
  }
  ```
- **业务价值**：高（采集中的常见问题）
- **工作量**：4-5h（Schema 设计 + Validator 规则 + UI 展示）
- **覆盖率提升**：+10-12%

**3. 临时措施的生命周期**
- **定义**：临时措施有明确的有效期（"3 个 lot 或 72 小时"）和失效条件（"三个月后又发生就失效"）
- **实现方式**：新增 `temporary_measure` 对象
  ```json
  {
    "retry_semantics": {
      "is_temporary": true,
      "expiration": {
        "duration": "PT72H",
        "lot_count": 3,
        "expiration_trigger": "duration_or_count"
      },
      "revocation_trigger": {
        "type": "time_passed|reoccurrence",
        "days": 90,
        "description": "三个月内同问题重现则自动失效"
      }
    }
  }
  ```
- **业务价值**：中高（Deviation 管理的重要部分）
- **工作量**：3-4h（Schema 设计 + Dashboard 扩展）
- **覆盖率提升**：+6-8%

**4. 多维 Containment 范围（简化版）**
- **定义**：不同的根本原因导致不同的追溯和隔离范围（按 LOT / Mold / Material / Line）
- **实现方式**：在 edge condition 中新增 `containment_scope` 映射
  ```json
  {
    "edge_condition": "equipment_issue_found",
    "action": "equipment_release_hold",
    "containment": {
      "dimension": "equipment_id",
      "rule": "all_products_on_same_equipment"
    }
  }
  ```
- **业务价值**：高（质量异常处理的核心）
- **工作量**：4-5h（Schema 设计 + UI 展示）
- **覆盖率提升**：+8-10%

**5. 简化版重试限制**
- **定义**："最多允许 reset 一次，第二次报同样 alarm 就不能再 reset"
- **实现方式**：在 `retry_semantics` 中新增 `escalation_on_repeat`
  ```json
  {
    "retry_semantics": {
      "max_retries_per_phase": 1,
      "escalation_on_repeat": {
        "enabled": true,
        "trigger": "same_condition",
        "action": "escalate_to_manager"
      }
    }
  }
  ```
- **业务价值**：中高（避免无限重试）
- **工作量**：2-3h（Schema 修改 + Validator 规则）
- **覆盖率提升**：+5-6%

---

#### ⚠️ P1（Phase 3-A 可选，或 Phase 3-B 规划）

这些维度的实现成本较高，或需要系统级设计。建议作为后续优化。

**6. 外部数据验证**（AVL、历史数据参考）
- **难度**：需要设计外部数据源的接口 + 动态查询逻辑
- **实现方式**：新增 `external_validation` 字段（但查询逻辑需要应用层实现）
- **工作量**：6-8h（Schema + 应用层集成）
- **推荐**：Phase 3-B（单独设计数据接口层）

**7. 量化的多维追溯（复杂版）**
- **难度**：追溯规则本身有条件逻辑（"如果前一批已经偏，那可能要追到上次 PM"）
- **实现方式**：需要规则引擎来评估条件
- **工作量**：8-10h（规则引擎设计 + 后端实现）
- **推荐**：Phase 3-B（与系统级规则引擎合并设计）

**8. 测试/检查强度的条件激励**
- **难度**：需要设计参数组合（"正常测 3 点 vs 换零件测 9 点"）
- **实现方式**：新增 `inspection_intensity_profile` 字段
- **工作量**：4-5h
- **推荐**：Phase 3-A 可选（如果有采集样本）

**9. 问题生命周期（CAPA 失效、重新打开）**
- **难度**：需要跟踪问题的多个状态和转移条件
- **实现方式**：需要独立的问题追踪模型（不能在工作流 Schema 中完全表示）
- **工作量**：10+ h
- **推荐**：Phase 3-B（单独的"问题管理"子系统）

---

#### ❌ P2（Phase 3-B 系统级，超出 Schema 范围）

这些维度属于系统架构问题，不能仅通过 Schema 扩展解决。

**10. 容量和瓶颈管理**
- **原因**：涉及全局排程、多流程协调
- **所需**：独立的容量规划模块

**11. 产品分批策略**
- **原因**：涉及全局生产计划
- **所需**：排程引擎集成

**12. 跨工作流规则**（采购、供应链）
- **原因**：超出单个工作流范围
- **所需**：规则引擎 + 流程管理系统

**13. 产品族级别的规则传播**
- **原因**：需要全局的产品族管理和配置
- **所需**：产品配置管理系统

---

## Phase 3-A 详细规划（优先实现）

### 工作分解

#### Task 1：Schema 扩展（聚合 + 权限 + 临时措施）
- **文件**：`workflow_graph_schema_v2.json`
- **变更**：
  1. 在 `evaluation_criterion` 中新增 `aggregation` 对象（可选）
  2. 在 node 中新增 `approval_matrix` 字段（可选）
  3. 在 `retry_semantics` 中新增 `is_temporary`、`expiration`、`revocation_trigger`
  4. 在 edge 中新增可选的 `containment_scope` 字段
- **工作量**：2-3h
- **产出**：更新的 Schema 定义

#### Task 2：示例数据和文档
- **文件**：`workflow_graph_v2_sample.json`、`PRD-SCHEMA-EXTENSION.md`
- **变更**：
  1. 添加一个演示聚合条件的示例
  2. 添加一个演示权限矩阵的示例
  3. 添加一个演示临时措施有效期的示例
  4. 更新 PRD 文档说明新字段
- **工作量**：2-3h
- **产出**：完整的示例 + 文档

#### Task 3：UI 设计规范更新
- **文件**：`UI-DESIGN-SLA-EVALUATION.md`
- **变更**：
  1. 在详情面板中新增"权限和签字"部分
  2. 在详情面板中新增"临时措施"部分
  3. 在评估规则中支持显示聚合条件（趋势图示）
  4. 在主 DAG 图上用小图标标识有权限限制的节点
- **工作量**：2-3h
- **产出**：更新的 UI 规范

#### Task 4：HTML 原型更新
- **文件**：`dag-sla-evaluation-redesign.html`
- **变更**：
  1. 添加权限签字部分的 UI 展示
  2. 添加临时措施信息的展示
  3. 演示聚合条件的趋势图
  4. 增加演示节点的数量或复杂性
- **工作量**：2-3h
- **产出**：更新的交互原型

#### Task 5：Validator 规则（新检查项）
- **文件**：应用代码 `validator.py` 或对应模块
- **变更**：
  1. 检查 `approval_matrix` 中的角色是否有效
  2. 检查 `aggregation.window_size` 的合理性
  3. 检查 `expiration_trigger` 的逻辑一致性
  4. 检查 `containment_scope` 引用的维度是否存在
- **工作量**：2-3h
- **产出**：Validator 规则代码

#### Task 6：LLM 采集提示词
- **文件**：应用代码 `guide_service.py` 或采集模块
- **变更**：
  1. P6 阶段新增问题：权限层级（谁能批准？分级吗？）
  2. P6 阶段新增问题：临时措施有效期（多久失效？）
  3. 决策节点新增问题：条件是单点还是趋势？
  4. 异常处理阶段新增问题：追溯范围按什么维度？
- **工作量**：2-3h
- **产出**：更新的采集流程提示词

### 总工作量：Phase 3-A
- **估计**：14-18h（如果并行进行，可压缩到 10-12h）
- **覆盖率提升**：+30-40%
- **新的总覆盖率**：65-75%

---

## 覆盖率对比

### Phase 1/2 完成后（现状）
```
■■■■■■■■■■□□□□□□□□□□  35-40%
```

### Phase 3-A 完成后（目标）
```
■■■■■■■■■■■■■■■■■□□□  65-75%
```

### Phase 3-B 完成后（远期）
```
■■■■■■■■■■■■■■■■■■■■  90%+
```

---

## 风险评估

### Phase 3-A 风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 权限矩阵设计过于复杂 | 采集难度上升 | 设计通用的预设模板 |
| 聚合条件的计算逻辑复杂 | UI 展示困难 | 使用可视化图表简化展示 |
| 多维 Containment 难以表示 | Schema 会变复杂 | 先实现简化版本，支持单维规则 |

### 应对方案

1. **从最高价值维度开始**：权限分级（采集中最常见）
2. **先做示例和文档**，再做代码
3. **每个任务做完就测试**，不要等到全部完成

---

## 决策清单

在启动 Phase 3-A 之前，需要确认：

- [ ] 优先实现权限分级、聚合条件、临时措施这三个维度？
- [ ] 是否投入资源做 Phase 3-B 的长期规划（外部数据、问题生命周期）？
- [ ] 采集系统是否准备好支持更复杂的 LLM 提示词？
- [ ] 是否有真实采集样本来验证新设计？

---

## 后续步骤

### 立即行动（本周）

1. **验证**：从前面的 5 个真实例子中选出 1-2 个，用新增的维度重新结构化
2. **确认**：与专家讨论这些新维度是否确实覆盖了他们的表述
3. **优先级**：根据采集样本的实际需求调整 P0/P1 的分类

### 短期行动（2 周内）

1. **实现 Phase 3-A 的前 2 个任务**（Schema + 示例数据）
2. **创建 Phase 3-A 的实现 Checklist**
3. **准备 Phase 3-B 的架构设计文档**

---

## 相关文件

- `PRD-SCHEMA-EXTENSION.md` - Phase 1/2 的完整设计
- `UI-DESIGN-SLA-EVALUATION.md` - 现有 UI 规范
- `IMPLEMENTATION-SUMMARY.md` - 工作进度记录
- `workflow_graph_v2_sample.json` - 示例数据

---

**下一步决策**：确认是否启动 Phase 3-A？优先实现哪 3-5 个维度？
