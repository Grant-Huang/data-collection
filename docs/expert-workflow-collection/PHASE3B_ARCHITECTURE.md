# Phase 3-B 架构设计

## 系统架构概述

Phase 3-B 扩展了 Phase 3-A 验证框架，引入系统级规则、跨工作流关系和全局政策的管理。整个系统分为四层：

```
┌─────────────────────────────────────────────────┐
│          REST API Layer (FastAPI Routes)        │
│        /api/phase3b/system-rules                │
│        /api/phase3b/workflow-relationships      │
│        /api/phase3b/global-policies             │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│         Application Logic Layer                 │
│  ┌──────────────┐  ┌──────────────┐            │
│  │RulesManager  │  │Validators    │            │
│  │  - CRUD      │  │  - Validate  │            │
│  │  - Versioning│  │  - Conflict  │            │
│  │  - Audit     │  │  - Impact    │            │
│  └──────────────┘  └──────────────┘            │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│         Data Models Layer (Pydantic)            │
│  ┌──────────────┐  ┌──────────────┐            │
│  │SystemRule    │  │Relationship  │            │
│  │GlobalPolicy  │  │Constraints   │            │
│  └──────────────┘  └──────────────┘            │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│      Storage Layer (Database Cache)             │
│  - JSON storage in db.get_cache/set_cache       │
│  - Version history tracking                     │
│  - Audit trail logging                          │
└─────────────────────────────────────────────────┘
```

## 核心组件

### 1. 数据模型 (`models.py`)

#### SystemRule 类
- **用途**: 定义系统级约束和政策
- **字段**:
  - `rule_type`: 规则类型（validation_constraint, permission_requirement等）
  - `content`: 规则具体内容（JSON，结构因rule_type而异）
  - `applicable_workflow_types`: 应用范围（空列表表示全部）
  - `version`: 语义版本号
  - `status`: draft/active/deprecated/archived

#### WorkflowRelationship 类
- **用途**: 管理工作流间的依赖和约束
- **字段**:
  - `relationship_type`: 依赖类型（dependency, data_handoff, parallel_split等）
  - `constraints`: 时间约束、数据约束等
  - `has_circular_dependency`: 循环依赖标志（由检测器设置）

#### GlobalPolicy 类
- **用途**: 定义组织级或部门级的决策规则
- **字段**:
  - `scope`: 政策适用范围（organization, department, workflow_type）
  - `decision_rules`: 条件-行动对列表
  - `exception_handlers`: 异常处理规则

### 2. 规则管理器 (`rules_manager.py`)

**RulesManager 类** - 中央规则库的核心

```python
class RulesManager:
    # 存储键（数据库中的键）
    SYSTEM_RULES_KEY = "phase3b:system_rules"
    RELATIONSHIPS_KEY = "phase3b:relationships"
    POLICIES_KEY = "phase3b:policies"
    RULE_VERSIONS_KEY = "phase3b:rule_versions"
```

**主要方法**:

1. **SystemRule 管理**
   - `create_system_rule()`: 创建规则（status=draft）
   - `get_system_rule()`: 获取单个规则
   - `list_system_rules()`: 列表查询（支持过滤）
   - `update_system_rule()`: 更新规则（自动版本升级）
   - `activate_system_rule()`: 激活规则（draft -> active）

2. **WorkflowRelationship 管理**
   - `create_workflow_relationship()`: 创建关系
   - `get_workflow_relationship()`: 获取关系
   - `list_workflow_relationships()`: 列表查询
   - `update_workflow_relationship()`: 更新关系

3. **GlobalPolicy 管理**
   - `create_global_policy()`: 创建政策
   - `get_global_policy()`: 获取政策
   - `list_global_policies()`: 列表查询
   - `update_global_policy()`: 更新政策

4. **版本控制**
   - `_record_version()`: 记录每次修改
   - 保留最近100条版本历史

### 3. 验证器 (`phase3b_validators.py`)

#### SystemRuleValidator
- 验证规则名称唯一性
- 验证日期逻辑（有效期）
- 验证内容格式（根据rule_type）
- 验证权限和审批状态

#### WorkflowRelationshipValidator
- 验证源和目标工作流存在
- 检测自引用
- 验证时间约束合理性
- **循环依赖检测**（使用DFS）:
  ```
  算法: 对每个节点执行DFS
    - visited: 已访问节点集合
    - rec_stack: 递归栈（用于检测当前路径中的循环）
    - 如果访问已在rec_stack中的节点，则存在循环
  ```

#### GlobalPolicyValidator
- 验证政策名称和范围
- 验证决策规则完整性
- 验证scope_target的必要性

#### ConflictDetector
- **权限冲突检测**: 检测相互矛盾的角色要求
- **政策冲突检测**: 检测同范围的冲突规则

#### ImpactAnalyzer
- 计算受影响工作流数量
- 评估风险等级
  - `critical`: 影响>100个工作流或涉及compliance
  - `high`: 影响>50个工作流或privilege升级
  - `medium`: 影响>10个工作流
  - `low`: 其他情况
- 生成实施建议

### 4. REST API (`routers/phase3b_rules.py`)

**端点结构**:

```
/api/phase3b/
├── system-rules/
│   ├── POST   / (创建)
│   ├── GET    / (列表)
│   ├── GET    /{id} (详情)
│   ├── PATCH  /{id} (更新)
│   ├── POST   /{id}/activate (激活)
│   ├── GET    /{id}/validate (验证)
│   └── GET    /{id}/impact (影响分析)
├── workflow-relationships/
│   ├── POST   / (创建)
│   ├── GET    / (列表)
│   ├── GET    /{id} (详情)
│   ├── PATCH  /{id} (更新)
│   └── GET    /detect-cycles (循环检测)
├── global-policies/
│   ├── POST   / (创建)
│   ├── GET    / (列表)
│   ├── GET    /{id} (详情)
│   └── PATCH  /{id} (更新)
├── conflicts/
│   ├── GET    /permissions (权限冲突)
│   └── GET    /policies (政策冲突)
└── health (健康检查)
```

## 数据流

### 创建规则流程

```
User Request
    ↓
POST /api/phase3b/system-rules
    ↓
RulesManager.create_system_rule()
    ├─ 生成rule_id (uuid)
    ├─ 设置版本: 1.0.0
    ├─ 设置状态: draft
    ├─ 记录创建时间和用户
    └─ 保存到 db.get_cache("phase3b:system_rules")
    ↓
SystemRuleValidator.validate()
    ├─ 检查基本字段
    ├─ 验证日期范围
    └─ 验证内容格式
    ↓
返回 Rule + Validation Issues
```

### 激活规则流程

```
POST /api/phase3b/system-rules/{id}/activate
    ↓
RulesManager.activate_system_rule()
    ├─ 检查当前状态是否为 draft
    ├─ 更新状态为 active
    ├─ 设置 effective_date
    ├─ 版本升级 1.0.0 -> 1.0.1
    └─ 记录变更
    ↓
ImpactAnalyzer.analyze_rule_change_impact()
    ├─ 找到受影响工作流
    ├─ 评估风险等级
    └─ 生成实施建议
    ↓
返回激活的规则 + 影响分析
```

### 关系创建与循环检测流程

```
POST /api/phase3b/workflow-relationships
    ↓
RulesManager.create_workflow_relationship()
    └─ 保存关系到 db.get_cache("phase3b:relationships")
    ↓
WorkflowRelationshipValidator.validate()
    └─ 检查基本字段和约束
    ↓
WorkflowRelationshipValidator.detect_cycles()
    ├─ 构建邻接表（图）
    ├─ 对每个节点执行DFS
    ├─ 追踪递归栈
    └─ 返回所有循环路径
    ↓
如果有循环 → 日志警告 + 返回循环信息
```

## 版本控制机制

### 版本升级规则

1. **创建时**: `1.0.0`
2. **更新内容时**: 次版本号 +1
   - `1.0.0` → `1.0.1`
   - `1.0.1` → `1.0.2`
3. **主版本号升级**: 手动设置（表示不兼容变更）

### 版本历史存储

```python
# 键: "phase3b:rule_versions:system_rule:{rule_id}"
# 值:
[
  {
    "timestamp": "2026-10-07T10:00:00Z",
    "operation": "created",
    "user_id": "admin@example.com",
    "entity_data": {...}  // 完整规则数据快照
  },
  {
    "timestamp": "2026-10-07T11:00:00Z",
    "operation": "updated",
    "user_id": "manager@example.com",
    "entity_data": {...}  // 更新后的完整数据
  }
]
```

## 存储架构

### 数据库键结构

```
phase3b:system_rules
  {
    "rule_abc123": {...},  // 序列化的规则对象
    "rule_def456": {...}
  }

phase3b:relationships
  {
    "rel_ghi789": {...},   // 序列化的关系对象
    "rel_jkl012": {...}
  }

phase3b:policies
  {
    "policy_mno345": {...}, // 序列化的政策对象
    "policy_pqr678": {...}
  }

phase3b:rule_versions:system_rule:rule_abc123
  [
    {
      "timestamp": "...",
      "operation": "...",
      "user_id": "...",
      "entity_data": {...}
    }
  ]
```

## 验证流程

### 三层验证

1. **API 参数验证** (Pydantic)
   - 字段类型检查
   - 必填字段检查
   - Enum值验证

2. **业务逻辑验证** (Validators)
   - 规则内容合理性
   - 约束条件一致性
   - 范围覆盖完整性

3. **冲突和影响检测** (ConflictDetector/ImpactAnalyzer)
   - 跨规则冲突
   - 循环依赖
   - 影响范围评估

## 性能考虑

### 查询优化
- 使用内存缓存存储规则
- 支持按status/type过滤减少遍历
- 循环检测使用DFS（O(V+E)）

### 缓存策略
- 规则加载：按需加载整个规则集到内存
- 版本历史：只保留最近100条
- 检测结果：动态计算（不缓存）

### 扩展性
- 当规则数>1000时考虑分区存储
- 版本历史可独立迁移到冷存储
- 定期清理过期规则和版本

## 扩展点

### 1. 新的规则类型
添加到 `RuleType` Literal：
```python
RuleType = Literal[
    "validation_constraint",
    "permission_requirement",
    # ... 新类型
]
```

在 `SystemRuleValidator._validate_content()` 中添加验证逻辑

### 2. 新的约束类型
继承 `BaseModel` 创建新约束类，在 `WorkflowRelationship.constraints` 中使用Union

### 3. 新的决策规则
扩展 `GlobalPolicy.decision_rules` 的结构和验证逻辑

## 安全考虑

1. **权限控制**: API层应验证 `created_by`/`updated_by` 用户权限
2. **审计日志**: 所有操作都记录用户和时间戳
3. **版本隔离**: 版本历史不可修改，只可追加
4. **输入验证**: 所有用户输入通过Pydantic模型验证

---

**版本**: 1.0.0  
**最后更新**: 2026-10-07  
**下一步**: Stage 2 架构设计
