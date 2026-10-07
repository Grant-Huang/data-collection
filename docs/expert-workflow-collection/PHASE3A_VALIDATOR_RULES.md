# Phase 3-A Validator 规则设计文档

本文档定义了如何在数据验证层实现 Phase 3-A 新维度的校验规则。

## 概述

Validator 是确保数据质量的重要环节。对于 Phase 3-A 新增的字段，需要添加以下验证规则：

1. **权限矩阵验证** - approval_matrix 字段
2. **聚合条件验证** - evaluation_criterion.aggregation 字段
3. **临时措施验证** - retry_semantics 中的临时措施字段
4. **隔离范围验证** - containment_scope 字段

---

## Validator 规则详细设计

### 规则 1: 权限矩阵完整性验证

**目标**：确保 approval_matrix 中的角色和条件有效且逻辑一致

**适用字段**：`node.approval_matrix`

**验证逻辑**：

```python
def validate_approval_matrix(node_id, approval_matrix):
    """
    验证 approval_matrix 的有效性
    
    Args:
        node_id: 节点 ID
        approval_matrix: 批准矩阵数组
    
    Returns:
        List[ValidationError]: 验证错误列表
    """
    errors = []
    
    if not approval_matrix:
        return errors  # 可选字段，可为空
    
    if not isinstance(approval_matrix, list):
        errors.append(ValidationError(
            node_id,
            'approval_matrix',
            'must_be_array',
            'approval_matrix 必须是数组'
        ))
        return errors
    
    # 定义有效的角色集合（可从系统配置获取）
    valid_roles = {
        'equipment_engineer', 'process_engineer', 'quality_engineer',
        'production_manager', 'executive', 'other'
    }
    
    for i, approval in enumerate(approval_matrix):
        # 检查必填字段
        if not approval.get('approval_type'):
            errors.append(ValidationError(
                node_id,
                f'approval_matrix[{i}].approval_type',
                'required_field',
                f'第 {i+1} 项批准的 approval_type 不能为空'
            ))
        
        # 检查 required_roles 有效性
        if not approval.get('required_roles'):
            errors.append(ValidationError(
                node_id,
                f'approval_matrix[{i}].required_roles',
                'required_field',
                f'第 {i+1} 项批准的 required_roles 不能为空'
            ))
        else:
            for role in approval['required_roles']:
                if role not in valid_roles:
                    errors.append(ValidationError(
                        node_id,
                        f'approval_matrix[{i}].required_roles',
                        'invalid_role',
                        f'不认可的角色：{role}'
                    ))
        
        # 检查 sequence 的有效值
        if approval.get('sequence') not in ['parallel', 'sequential']:
            errors.append(ValidationError(
                node_id,
                f'approval_matrix[{i}].sequence',
                'invalid_value',
                f'sequence 必须是 parallel 或 sequential，不能为 {approval.get("sequence")}'
            ))
        
        # 检查 criteria 不为空（非常重要）
        if not approval.get('criteria'):
            errors.append(ValidationError(
                node_id,
                f'approval_matrix[{i}].criteria',
                'required_field',
                f'第 {i+1} 项批准的 criteria（评估标准）不能为空'
            ))
        
        # 检查 escalation_level 的有效性（如果提供）
        if approval.get('escalation_level') is not None:
            if not isinstance(approval['escalation_level'], int):
                errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}].escalation_level',
                    'invalid_type',
                    'escalation_level 必须是整数'
                ))
            elif approval['escalation_level'] < 1:
                errors.append(ValidationError(
                    node_id,
                    f'approval_matrix[{i}].escalation_level',
                    'invalid_value',
                    'escalation_level 必须 >= 1'
                ))
    
    # 逻辑检查：如果是顺序批准，不能有重复的角色
    if len(approval_matrix) > 1:
        all_roles = []
        for approval in approval_matrix:
            all_roles.extend(approval.get('required_roles', []))
        
        duplicates = [role for role in set(all_roles) if all_roles.count(role) > 1]
        if duplicates:
            errors.append(ValidationError(
                node_id,
                'approval_matrix',
                'duplicate_roles',
                f'批准矩阵中出现重复角色，可能会导致流程问题：{duplicates}'
            ))
    
    return errors
```

**严重级别**：HIGH（如果节点标记为需要批准，但 approval_matrix 无效，应阻止发布）

---

### 规则 2: 聚合条件参数验证

**目标**：确保聚合条件的参数有效且逻辑一致

**适用字段**：`evaluation_criterion.aggregation`

**验证逻辑**：

```python
def validate_aggregation(criterion_id, aggregation):
    """
    验证聚合条件的有效性
    
    Args:
        criterion_id: 评估标准 ID
        aggregation: 聚合条件对象
    
    Returns:
        List[ValidationError]: 验证错误列表
    """
    errors = []
    
    if not aggregation:
        return errors  # 可选字段，可为空
    
    # 检查必填字段
    required_fields = ['method', 'window_size', 'operator', 'min_samples']
    for field in required_fields:
        if aggregation.get(field) is None:
            errors.append(ValidationError(
                criterion_id,
                f'aggregation.{field}',
                'required_field',
                f'aggregation.{field} 不能为空'
            ))
    
    # 检查 method 的有效值
    valid_methods = ['trend', 'pattern', 'continuous', 'statistical']
    if aggregation.get('method') not in valid_methods:
        errors.append(ValidationError(
            criterion_id,
            'aggregation.method',
            'invalid_value',
            f"method 必须是 {valid_methods} 之一，不能为 {aggregation.get('method')}"
        ))
    
    # 检查 window_size（必须是正整数）
    window_size = aggregation.get('window_size')
    if window_size is not None:
        if not isinstance(window_size, int) or window_size <= 0:
            errors.append(ValidationError(
                criterion_id,
                'aggregation.window_size',
                'invalid_type',
                f'window_size 必须是正整数，不能为 {window_size}'
            ))
        elif window_size < 2:
            errors.append(ValidationError(
                criterion_id,
                'aggregation.window_size',
                'insufficient_window',
                f'window_size 应至少为 2（用于趋势判断），当前值：{window_size}'
            ))
        elif window_size > 100:
            errors.append(ValidationError(
                criterion_id,
                'aggregation.window_size',
                'warning',  # 仅警告，不阻止
                f'window_size 很大（{window_size}），可能导致计算缓慢，建议 <= 50'
            ))
    
    # 检查 operator 的有效值
    valid_operators = ['all_increasing', 'all_decreasing', 'two_exceeding', 
                       'variance_above', 'mean_shift', 'cycle_detected']
    if aggregation.get('operator') not in valid_operators:
        errors.append(ValidationError(
            criterion_id,
            'aggregation.operator',
            'invalid_value',
            f"operator 必须是 {valid_operators} 之一"
        ))
    
    # 检查 min_samples（必须小于等于 window_size）
    min_samples = aggregation.get('min_samples')
    if min_samples is not None:
        if not isinstance(min_samples, int) or min_samples <= 0:
            errors.append(ValidationError(
                criterion_id,
                'aggregation.min_samples',
                'invalid_type',
                f'min_samples 必须是正整数，不能为 {min_samples}'
            ))
        elif min_samples > window_size:
            errors.append(ValidationError(
                criterion_id,
                'aggregation.min_samples',
                'invalid_logic',
                f'min_samples ({min_samples}) 不能大于 window_size ({window_size})'
            ))
    
    # 检查 threshold（如果提供，格式应该能被系统理解）
    threshold = aggregation.get('threshold')
    if threshold:
        # 这里可以添加特定于域的验证（如温度范围、百分比等）
        if not isinstance(threshold, str):
            errors.append(ValidationError(
                criterion_id,
                'aggregation.threshold',
                'invalid_type',
                f'threshold 必须是字符串，不能为 {type(threshold).__name__}'
            ))
    
    # 检查 description（建议非空）
    if not aggregation.get('description'):
        errors.append(ValidationError(
            criterion_id,
            'aggregation.description',
            'recommended_field',
            'aggregation.description 建议填写，有助于理解聚合条件的含义'
        ))
    
    return errors
```

**严重级别**：HIGH（聚合参数错误会导致条件判断失败）

---

### 规则 3: 临时措施有效期验证

**目标**：确保临时措施的有效期配置合理且可执行

**适用字段**：`node.retry_semantics`（当 is_temporary=true 时）

**验证逻辑**：

```python
def validate_temporary_measure(node_id, retry_semantics):
    """
    验证临时措施（临时性重试）的配置
    
    Args:
        node_id: 节点 ID
        retry_semantics: 重试语义配置
    
    Returns:
        List[ValidationError]: 验证错误列表
    """
    errors = []
    
    if not retry_semantics or not retry_semantics.get('is_temporary'):
        return errors  # 不是临时措施，跳过检查
    
    # 检查 expiration 配置
    expiration = retry_semantics.get('expiration')
    if not expiration:
        errors.append(ValidationError(
            node_id,
            'retry_semantics.expiration',
            'required_when_temporary',
            '当 is_temporary=true 时，expiration 配置不能为空'
        ))
        return errors
    
    # 检查 duration 的有效性（ISO 8601 格式）
    duration = expiration.get('duration')
    if duration:
        # 简单验证：应以 PT 开头（ISO 8601 Duration）
        if not (duration.startswith('PT') or duration.endswith('h')):
            errors.append(ValidationError(
                node_id,
                'retry_semantics.expiration.duration',
                'invalid_format',
                f'duration 格式应为 ISO 8601（如 PT72H）或自然语言（如 72h），当前值：{duration}'
            ))
    
    # 检查 lot_count（必须是正整数）
    lot_count = expiration.get('lot_count')
    if lot_count is not None:
        if not isinstance(lot_count, int) or lot_count <= 0:
            errors.append(ValidationError(
                node_id,
                'retry_semantics.expiration.lot_count',
                'invalid_type',
                f'lot_count 必须是正整数，不能为 {lot_count}'
            ))
    
    # 检查 expiration_trigger 的有效值
    trigger = expiration.get('expiration_trigger')
    valid_triggers = ['duration_or_count', 'duration_and_count']
    if trigger not in valid_triggers:
        errors.append(ValidationError(
            node_id,
            'retry_semantics.expiration.expiration_trigger',
            'invalid_value',
            f'expiration_trigger 必须是 {valid_triggers} 之一'
        ))
    
    # 检查 revocation_trigger（失效条件）
    revocation = retry_semantics.get('revocation_trigger')
    if revocation:
        rev_type = revocation.get('type')
        valid_rev_types = ['time_passed', 'reoccurrence', 'condition_met']
        if rev_type not in valid_rev_types:
            errors.append(ValidationError(
                node_id,
                'retry_semantics.revocation_trigger.type',
                'invalid_value',
                f'type 必须是 {valid_rev_types} 之一'
            ))
        
        # 如果是时间相关，检查 days
        if rev_type == 'time_passed' and revocation.get('days') is None:
            errors.append(ValidationError(
                node_id,
                'retry_semantics.revocation_trigger.days',
                'required_field',
                '当 revocation_trigger.type=time_passed 时，days 字段必须提供'
            ))
    
    # 检查 escalation_on_repeat
    escalation = retry_semantics.get('escalation_on_repeat')
    if escalation and escalation.get('enabled'):
        if not escalation.get('action'):
            errors.append(ValidationError(
                node_id,
                'retry_semantics.escalation_on_repeat.action',
                'required_field',
                'escalation_on_repeat 启用时，action 字段必须提供'
            ))
        else:
            valid_actions = ['escalate_to_manager', 'escalate_to_executive', 
                           'create_capa', 'stop_production']
            if escalation['action'] not in valid_actions:
                errors.append(ValidationError(
                    node_id,
                    'retry_semantics.escalation_on_repeat.action',
                    'invalid_value',
                    f"action 必须是 {valid_actions} 之一"
                ))
    
    # 逻辑检查：临时措施应该限制重试次数
    if retry_semantics.get('max_retries_per_phase') is None:
        errors.append(ValidationError(
            node_id,
            'retry_semantics.max_retries_per_phase',
            'recommended_field',
            '临时措施建议设置 max_retries_per_phase 来限制重试次数'
        ))
    
    return errors
```

**严重级别**：HIGH（临时措施配置不当会导致流程管理混乱）

---

### 规则 4: 隔离范围维度验证

**目标**：确保隔离范围配置的维度和规则有效

**适用字段**：`node.containment_scope` 和 `edge.containment_scope`

**验证逻辑**：

```python
def validate_containment_scope(object_id, containment, context='node'):
    """
    验证隔离范围配置
    
    Args:
        object_id: 节点或边的 ID
        containment: 隔离范围配置
        context: 上下文（'node' 或 'edge'）
    
    Returns:
        List[ValidationError]: 验证错误列表
    """
    errors = []
    
    if not containment:
        return errors  # 可选字段，可为空
    
    # 检查 dimension 的有效值
    valid_dimensions = ['equipment_id', 'lot_id', 'material_id', 
                       'line_id', 'mold_id', 'shift_id']
    dimension = containment.get('dimension')
    if dimension not in valid_dimensions:
        errors.append(ValidationError(
            object_id,
            'containment_scope.dimension',
            'invalid_value',
            f'dimension 必须是 {valid_dimensions} 之一，不能为 {dimension}'
        ))
    
    # 检查 rule 不为空
    if not containment.get('rule'):
        errors.append(ValidationError(
            object_id,
            'containment_scope.rule',
            'required_field',
            'containment_scope.rule 不能为空'
        ))
    
    # 检查 applicable_conditions（如果提供）
    conditions = containment.get('applicable_conditions')
    if conditions is not None:
        if not isinstance(conditions, list):
            errors.append(ValidationError(
                object_id,
                'containment_scope.applicable_conditions',
                'invalid_type',
                'applicable_conditions 必须是数组'
            ))
        elif len(conditions) == 0:
            errors.append(ValidationError(
                object_id,
                'containment_scope.applicable_conditions',
                'recommended_field',
                '建议提供 applicable_conditions，说明此隔离规则何时适用'
            ))
    
    # 逻辑检查：某些维度需要其他关联信息
    if dimension == 'equipment_id' and context == 'edge':
        # 边的隔离应该来自节点的决策
        pass  # 这可能需要跨节点的上下文检查
    
    return errors
```

**严重级别**：HIGH（隔离范围错误会导致产品隔离不完整或过度隔离）

---

### 规则 5: 本体维度验证（阈值 / escalation / 证据）

实现位置：`src/validators/phase3a_validator.py`。严重级别沿用现有口径：声明了某个特性却缺少让它可执行的关键字段 → ERROR；能用但含义不完整 → WARNING。

| 代码 | 级别 | 触发条件 | 字段 |
|------|------|----------|------|
| `threshold_missing_unit` | WARNING | `thresholds` 或 `aggregation.threshold` 中出现裸数字（如 `"50"`、`"< 40"`），且 `unit` 为空。阈值自带单位（如 `"3°C"`、`"< 85%"`）视为自描述，不报 | `evaluation_criteria[i].unit` |
| `metric_missing_threshold` | WARNING | `type` 为 `metric` / `numeric_range`，但既没有非空 `thresholds` 也没有 `aggregation`（缺阈值/预期值） | `evaluation_criteria[i].thresholds` |
| `escalation_missing_receiver` | ERROR | `sla_config.violation_action == "escalate"` 但没有 `sla_config.escalate_to_roles`（超期后无人接手） | `sla_config.escalate_to_roles` |
| `escalation_missing_receiver` | WARNING | `escalation_on_repeat.enabled` 且 `action` 为 `escalate_to_manager` / `escalate_to_executive`，但没有 `escalate_to_roles`（action 只给了级别） | `retry_semantics.escalation_on_repeat.escalate_to_roles` |
| `required_field` | ERROR | `escalation_on_repeat.enabled` 但没有 `action` | `retry_semantics.escalation_on_repeat.action` |
| `invalid_role` / `type_error` | ERROR | `escalate_to_roles` 不是数组，或含 `VALID_ROLES` 以外的角色（与权限矩阵一致） | `*.escalate_to_roles` |
| `evidence_missing_source` | WARNING | 节点或边既没有 `source_turn_ids`，也没有 `expert_confirmed`（PRD：抽取结果须可追溯）。`start` / `end` 结构节点跳过 | `source_turn_ids` |
| `type_error` | ERROR | `source_turn_ids` 不是数组 | `source_turn_ids` |
| `invalid_confidence` | ERROR | `confidence` 不是 0–1 之间的数（schema 的 minimum/maximum） | `confidence` |

`create_capa` / `stop_production` 是处置动作而非移交，不要求接收角色。`escalate_to_roles` 是本规则新增到 schema（`sla_config` 与 `escalation_on_repeat`）的字段。

证据维度由 `Phase3AValidator.validate_evidence(obj, kind)` 实现，`SchemaValidator.validate_graph` 对每个节点和每条边调用；其余规则在 `validate_node` 中执行。每条结果带 `object_kind`（`node` / `edge`），`phase3a_integration.convert_to_legacy_issues` 据此填入 `node_id` 或 `edge_id`，与 `graph_validator` 的 issue 格式一致。

---

## Validator 执行流程

### 集成点

```python
class SchemaValidator:
    """
    Phase 3-A 的 Validator 集成
    """
    
    def validate_node(self, node):
        """验证单个节点"""
        errors = []
        
        # Phase 1/2 现有检查
        # ... 现有代码 ...
        
        # Phase 3-A 新增检查
        if node.get('approval_matrix'):
            errors.extend(validate_approval_matrix(node['node_id'], node['approval_matrix']))
        
        if node.get('evaluation_criteria'):
            for criterion in node['evaluation_criteria']:
                if criterion.get('aggregation'):
                    errors.extend(validate_aggregation(criterion['id'], criterion['aggregation']))
        
        if node.get('retry_semantics'):
            errors.extend(validate_temporary_measure(node['node_id'], node['retry_semantics']))
        
        if node.get('containment_scope'):
            errors.extend(validate_containment_scope(node['node_id'], node['containment_scope'], 'node'))
        
        return errors
    
    def validate_edge(self, edge):
        """验证单条边"""
        errors = []
        
        # Phase 1/2 现有检查
        # ... 现有代码 ...
        
        # Phase 3-A 新增检查
        if edge.get('containment_scope'):
            errors.extend(validate_containment_scope(edge['edge_id'], edge['containment_scope'], 'edge'))
        
        return errors
```

---

## 错误分类和处理

### 严重级别定义

- **ERROR**（红色）：阻止保存，必须修复
- **WARNING**（黄色）：允许保存，但标记为"需要审核"
- **INFO**（蓝色）：仅提示，不影响保存

### 示例错误消息

```json
{
    "error": {
        "object_id": "n5",
        "field": "approval_matrix[0].required_roles",
        "code": "invalid_role",
        "message": "不认可的角色：xxx_engineer",
        "suggestion": "请从以下角色中选择：equipment_engineer, process_engineer, quality_engineer, ...",
        "severity": "ERROR"
    }
}
```

---

## 测试用例

### 测试 1: 权限矩阵有效性

```json
{
    "node_id": "n5",
    "approval_matrix": [
        {
            "approval_type": "equipment_release",
            "required_roles": ["equipment_engineer"],
            "sequence": "sequential",
            "criteria": "设备状态正常"
        }
    ],
    "expected": "PASS"
}
```

### 测试 2: 聚合条件窗口过大

```json
{
    "criterion_id": "temp_trend",
    "aggregation": {
        "method": "trend",
        "window_size": 500,  // 太大
        "operator": "all_increasing",
        "min_samples": 5
    },
    "expected": "WARNING: window_size 很大"
}
```

### 测试 3: 临时措施缺少有效期

```json
{
    "node_id": "n6",
    "retry_semantics": {
        "is_temporary": true,
        "expiration": null  // 缺少
    },
    "expected": "ERROR: expiration 不能为空"
}
```

---

## 实现计划

1. **代码实现**（2-3h）
   - 在 validator.py 或对应模块中添加上述函数
   - 集成到现有的 Validator 流程

2. **单元测试**（1-2h）
   - 为每个规则编写测试用例
   - 覆盖正常情况和边界情况

3. **集成测试**（1h）
   - 测试与其他 Validator 规则的交互
   - 测试错误消息的清晰性

4. **文档补充**（0.5h）
   - 更新用户文档，说明新的验证规则
   - 提供错误解决指南

**总工作量**：4.5-6.5 小时

---

**文档版本**：1.0  
**日期**：2026-10-07  
**状态**：设计完成，可直接用于实现
