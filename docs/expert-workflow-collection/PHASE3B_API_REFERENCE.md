# Phase 3-B API 参考

## 概述

Phase 3-B REST API 提供系统规则、工作流关系、全局政策的完整CRUD操作和管理功能。所有API都通过 `/api/phase3b` 前缀访问。

## 数据模型

### SystemRule（系统规则）
```json
{
  "rule_id": "rule_abc123",
  "rule_name": "Step Count Validation",
  "rule_type": "validation_constraint",
  "description": "Each workflow must have at least 3 steps",
  "content": {
    "constraint_expression": "step_count >= 3"
  },
  "status": "active",
  "version": "1.0.0",
  "effective_date": "2026-10-07T00:00:00Z",
  "expiry_date": null,
  "applicable_workflow_types": ["process_mapping", "standard_operation"],
  "applicable_stages": ["collecting", "confirmation"],
  "created_by": "admin@example.com",
  "created_at": "2026-10-07T10:00:00Z",
  "updated_by": "admin@example.com",
  "updated_at": "2026-10-07T10:00:00Z",
  "requires_approval": true,
  "approved_by": "manager@example.com",
  "approval_date": "2026-10-07T11:00:00Z",
  "estimated_affected_workflows": 150,
  "priority": "high",
  "tags": ["validation", "critical"]
}
```

### WorkflowRelationship（工作流关系）
```json
{
  "relationship_id": "rel_def456",
  "relationship_type": "dependency",
  "source_workflow_id": "wf_supplier_approval",
  "target_workflow_id": "wf_purchase_order",
  "description": "Supplier approval must complete before purchase order",
  "condition": "supplier_status == 'approved'",
  "constraints": [
    {
      "constraint_type": "time_constraint",
      "min_delay": 300,
      "max_delay": 86400,
      "deadline": "2026-10-14T00:00:00Z"
    }
  ],
  "version": "1.0.0",
  "status": "active",
  "created_by": "admin@example.com",
  "created_at": "2026-10-07T10:00:00Z",
  "updated_by": "admin@example.com",
  "updated_at": "2026-10-07T10:00:00Z",
  "has_circular_dependency": false,
  "has_deadlock_risk": false,
  "tags": ["supply_chain", "critical"]
}
```

### GlobalPolicy（全局政策）
```json
{
  "policy_id": "policy_ghi789",
  "policy_name": "Approval Policy",
  "description": "Global approval requirements for all workflows",
  "scope": "organization",
  "scope_target": null,
  "decision_rules": [
    {
      "rule_id": "dr_1",
      "rule_description": "Approval required for high-value items",
      "condition": "item_value > 10000",
      "action": "require_director_approval"
    }
  ],
  "exception_handlers": [
    {
      "exception_type": "timeout",
      "handling_strategy": "auto_escalate",
      "escalation_level": "manager",
      "auto_remediation": true,
      "remediation_action": "send_reminder"
    }
  ],
  "version": "1.0.0",
  "status": "active",
  "effective_date": "2026-10-07T00:00:00Z",
  "expiry_date": null,
  "created_by": "admin@example.com",
  "created_at": "2026-10-07T10:00:00Z",
  "updated_by": "admin@example.com",
  "updated_at": "2026-10-07T10:00:00Z",
  "requires_approval": true,
  "approved_by": "cto@example.com",
  "approval_date": "2026-10-07T12:00:00Z",
  "related_system_rules": ["rule_abc123"],
  "related_relationships": [],
  "priority": "critical",
  "tags": ["approval", "governance"]
}
```

## System Rules API

### 创建系统规则
```
POST /api/phase3b/system-rules
Content-Type: application/json

{
  "rule_name": "Step Count Validation",
  "rule_type": "validation_constraint",
  "description": "Each workflow must have at least 3 steps",
  "content": {
    "constraint_expression": "step_count >= 3"
  },
  "created_by": "admin@example.com",
  "applicable_workflow_types": ["process_mapping"],
  "priority": "high",
  "tags": ["validation"]
}

Response: 201 Created
{
  "rule_id": "rule_abc123",
  ...规则对象...
}
```

### 获取系统规则
```
GET /api/phase3b/system-rules/{rule_id}

Response: 200 OK
{
  "rule_id": "rule_abc123",
  ...规则对象...
}
```

### 列表查询系统规则
```
GET /api/phase3b/system-rules?status=active&rule_type=validation_constraint&workflow_type=process_mapping

Query Parameters:
- status: active | deprecated | draft | archived (可选)
- rule_type: validation_constraint | permission_requirement | ... (可选)
- workflow_type: 工作流类型 (可选)

Response: 200 OK
[
  {
    "rule_id": "rule_abc123",
    ...规则对象...
  },
  ...
]
```

### 更新系统规则
```
PATCH /api/phase3b/system-rules/{rule_id}
Content-Type: application/json

{
  "description": "Updated description",
  "priority": "critical",
  "expiry_date": "2026-12-31T23:59:59Z"
}

Response: 200 OK
{
  "rule_id": "rule_abc123",
  "version": "1.0.1",  // 版本自动增加
  ...更新后的规则对象...
}
```

### 激活系统规则
```
POST /api/phase3b/system-rules/{rule_id}/activate
Query Parameters:
- activated_by: 激活者邮箱

Response: 200 OK
{
  "rule_id": "rule_abc123",
  "status": "active",
  "effective_date": "2026-10-07T10:05:00Z",
  ...规则对象...
}
```

### 验证系统规则
```
GET /api/phase3b/system-rules/{rule_id}/validate

Response: 200 OK
[
  {
    "issue_id": "rule_no_name",
    "issue_type": "error",
    "code": "RULE_NAME_REQUIRED",
    "message": "规则名称不能为空",
    "affected_rule_id": "rule_abc123",
    "suggestion": "Please provide a non-empty rule name"
  }
]
```

### 分析规则影响
```
GET /api/phase3b/system-rules/{rule_id}/impact

Response: 200 OK
{
  "rule_id": "rule_abc123",
  "rule_type": "validation_constraint",
  "affected_workflow_ids": ["wf_1", "wf_2", ...],
  "affected_workflow_count": 150,
  "risk_level": "high",
  "estimated_impact_percentage": 45.5,
  "recommendations": [
    "大范围影响，建议分阶段实施",
    "规则需要审批，确保已获得必要的批准"
  ],
  "change_history": []
}
```

## Workflow Relationships API

### 创建工作流关系
```
POST /api/phase3b/workflow-relationships
Content-Type: application/json

{
  "relationship_type": "dependency",
  "source_workflow_id": "wf_supplier_approval",
  "target_workflow_id": "wf_purchase_order",
  "description": "Supplier approval must complete before purchase order",
  "created_by": "admin@example.com",
  "condition": "supplier_status == 'approved'",
  "constraints": [
    {
      "constraint_type": "time_constraint",
      "min_delay": 300,
      "max_delay": 86400
    }
  ],
  "tags": ["supply_chain"]
}

Response: 201 Created
{
  "relationship_id": "rel_def456",
  ...关系对象...
}
```

### 获取工作流关系
```
GET /api/phase3b/workflow-relationships/{rel_id}

Response: 200 OK
{
  "relationship_id": "rel_def456",
  ...关系对象...
}
```

### 列表查询工作流关系
```
GET /api/phase3b/workflow-relationships?source_workflow_id=wf_1&relationship_type=dependency

Query Parameters:
- source_workflow_id: 源工作流ID (可选)
- target_workflow_id: 目标工作流ID (可选)
- relationship_type: 关系类型 (可选)

Response: 200 OK
[
  {
    "relationship_id": "rel_def456",
    ...关系对象...
  }
]
```

### 更新工作流关系
```
PATCH /api/phase3b/workflow-relationships/{rel_id}
Content-Type: application/json

{
  "description": "Updated description",
  "constraints": [...]
}

Response: 200 OK
{
  "relationship_id": "rel_def456",
  "version": "1.0.1",
  ...更新后的关系对象...
}
```

### 检测循环依赖
```
GET /api/phase3b/workflow-relationships/detect-cycles

Response: 200 OK
{
  "cycles": {
    "wf_A": ["wf_A", "wf_B", "wf_C", "wf_A"]
  },
  "has_cycles": true
}
```

## Global Policies API

### 创建全局政策
```
POST /api/phase3b/global-policies
Content-Type: application/json

{
  "policy_name": "Approval Policy",
  "description": "Global approval requirements",
  "scope": "organization",
  "created_by": "admin@example.com",
  "decision_rules": [
    {
      "rule_id": "dr_1",
      "rule_description": "Approval required",
      "condition": "item_value > 10000",
      "action": "require_director_approval"
    }
  ],
  "priority": "critical",
  "tags": ["approval"]
}

Response: 201 Created
{
  "policy_id": "policy_ghi789",
  ...政策对象...
}
```

### 获取全局政策
```
GET /api/phase3b/global-policies/{policy_id}

Response: 200 OK
{
  "policy_id": "policy_ghi789",
  ...政策对象...
}
```

### 列表查询全局政策
```
GET /api/phase3b/global-policies?scope=organization&status=active

Query Parameters:
- scope: organization | department | workflow_type | all (可选)
- status: active | deprecated | draft | archived (可选)

Response: 200 OK
[
  {
    "policy_id": "policy_ghi789",
    ...政策对象...
  }
]
```

### 更新全局政策
```
PATCH /api/phase3b/global-policies/{policy_id}
Content-Type: application/json

{
  "decision_rules": [...],
  "priority": "high"
}

Response: 200 OK
{
  "policy_id": "policy_ghi789",
  "version": "1.0.1",
  ...更新后的政策对象...
}
```

## Conflict Detection API

### 检测权限冲突
```
GET /api/phase3b/conflicts/permissions

Response: 200 OK
{
  "conflict_count": 2,
  "conflicts": [
    {
      "rule1_id": "rule_abc",
      "rule2_id": "rule_def",
      "conflict_type": "Permission conflict"
    }
  ]
}
```

### 检测政策冲突
```
GET /api/phase3b/conflicts/policies

Response: 200 OK
{
  "conflict_count": 1,
  "conflicts": [
    {
      "policy1_id": "policy_1",
      "policy2_id": "policy_2",
      "conflict_type": "Scope overlap"
    }
  ]
}
```

## Health Check API

### 健康检查
```
GET /api/phase3b/health

Response: 200 OK
{
  "status": "ok",
  "service": "phase3b_rules",
  "version": "1.0.0"
}
```

## 错误响应

所有API在发生错误时返回以下格式：

```json
{
  "detail": "Error message describing what went wrong"
}
```

常见的HTTP状态码：
- `200 OK`: 成功
- `201 Created`: 资源创建成功
- `400 Bad Request`: 请求参数错误
- `404 Not Found`: 资源未找到
- `409 Conflict`: 冲突（如循环依赖）
- `500 Internal Server Error`: 服务器错误

## 版本控制

所有规则、关系、政策都支持语义版本控制（SemVer）：

- 创建时：`1.0.0`
- 更新内容时：次版本号增加（如 `1.0.1`）
- 主要变更时：主版本号增加（需要手动设置）

## 审计日志

所有修改操作都会记录：
- 操作人员 (created_by / updated_by)
- 操作时间 (created_at / updated_at)
- 变更历史 (change_history)
- 版本历史 (version tracking)

## 最佳实践

1. **规则激活**：从 `draft` 状态激活前，确保所有验证通过
2. **影响分析**：在激活高优先级规则前，运行影响分析
3. **循环检测**：创建工作流关系后，检查是否产生循环
4. **冲突检测**：定期运行冲突检测，发现潜在问题
5. **版本管理**：跟踪版本历史，支持规则回滚

---

**版本**: 1.0.0  
**最后更新**: 2026-10-07  
**下一步**: Phase 3-B Stage 2 (验证和监控)
