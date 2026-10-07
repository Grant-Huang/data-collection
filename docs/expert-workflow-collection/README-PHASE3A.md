# Phase 3-A 工作流采集系统扩展

## 📌 项目概述

本项目是对工作流采集系统的 Phase 3-A 扩展，旨在通过 4 个核心维度的 Schema 和采集优化，将系统对真实工作流的覆盖率从 **35-40% 提升到 65-75%**。

### 覆盖率目标

| 维度 | 当前 | 目标 | 改善 |
|---|---|---|---|
| 权限管理 | 30% | 85% | +55% |
| 聚合条件 | 20% | 90% | +70% |
| 临时措施 | 15% | 85% | +70% |
| 多维隔离 | 25% | 80% | +55% |
| **整体** | **35-40%** | **65-75%** | **+30-40%** |

---

## 🚀 实现现状（2026-10-07）

### ✅ 已完成（实现阶段）

#### 1. 核心代码实现
- **Validator 框架**（`src/validators/phase3a_validator.py`）
  - 567 行生产级代码
  - 4 个核心验证规则
  - 完整的错误分类和修复建议
  
- **单元测试**（`src/validators/test_phase3a_validator.py`）
  - 24 个测试用例，100% 通过
  - 覆盖所有验证规则和边界情况
  
- **LLM 采集模块**（`src/collection/phase3a_llm_prompts.py`）
  - 520 行代码
  - 20+ 精心设计的采集问题
  - 完整的采集工作流框架

#### 2. 用户界面
- **HTML 交互原型**（`dag-phase3a-enhanced.html`）
  - 22KB 交互式 SVG 原型
  - 6 个示例节点展示所有维度
  - 完整的动态详情面板

#### 3. 文档和示例
- **实现完成报告** - 详细的功能说明和集成指南
- **使用示例代码** - 5 个实用的代码示例
- **本 README** - 项目概览和后续步骤

### 📋 设计文档（已完成）

1. ✅ `schema/workflow_graph_schema_v2.json` - Schema 定义
2. ✅ `schema/PHASE3A_EXAMPLES.md` - 数据示例（396 行）
3. ✅ `UI-DESIGN-SLA-EVALUATION.md` - UI 规范（已扩展）
4. ✅ `PHASE3A_VALIDATOR_RULES.md` - Validator 规则设计
5. ✅ `PHASE3A_LLM_COLLECTION_PROMPTS.md` - LLM 采集设计
6. ✅ `PHASE3A_DELIVERY_SUMMARY.md` - 项目总结

---

## 📂 目录结构

```
data-collection/
├── docs/expert-workflow-collection/
│   ├── schema/
│   │   ├── workflow_graph_schema_v2.json          # Schema 定义
│   │   └── PHASE3A_EXAMPLES.md                    # 数据示例
│   ├── design/
│   │   ├── dag-phase3a-enhanced.html              # ✨ 交互式原型
│   │   └── PHASE3A_HTML_IMPLEMENTATION_GUIDE.md
│   ├── UI-DESIGN-SLA-EVALUATION.md               # UI 规范
│   ├── PHASE3A_VALIDATOR_RULES.md                # Validator 设计
│   ├── PHASE3A_LLM_COLLECTION_PROMPTS.md         # LLM 采集设计
│   ├── PHASE3A_DELIVERY_SUMMARY.md               # 项目总结
│   ├── PHASE3A_IMPLEMENTATION_COMPLETE.md        # ✨ 实现报告
│   └── README-PHASE3A.md                         # 本文件
├── src/
│   ├── __init__.py
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── phase3a_validator.py                  # ✨ Validator 实现
│   │   └── test_phase3a_validator.py             # ✨ 单元测试
│   └── collection/
│       ├── __init__.py
│       └── phase3a_llm_prompts.py               # ✨ LLM 采集模块
└── examples/
    └── phase3a_usage_examples.py                 # ✨ 使用示例
```

---

## 🔧 快速开始

### 1. 运行测试验证环境

```bash
cd src/validators
python -m unittest test_phase3a_validator -v
```

**预期输出**：
```
Ran 24 tests in 0.004s
OK
```

### 2. 验证数据结构

```bash
python examples/phase3a_usage_examples.py
```

这将运行 5 个示例，展示：
- ✅ 基本的数据验证流程
- ✅ 错误检测和报告
- ✅ 采集工作流规划
- ✅ 采集问题详情
- ✅ 权限矩阵结构

### 3. 查看交互式原型

在浏览器中打开：
```
docs/expert-workflow-collection/design/dag-phase3a-enhanced.html
```

点击任意节点查看详情面板。

---

## 📖 核心功能

### 功能 1：数据验证（Validator）

用于验证 Phase 3-A 新维度的数据完整性和逻辑一致性。

**关键规则**：
- 权限矩阵：角色有效性、批准标准、顺序检查
- 聚合条件：方法、窗口大小、操作符、样本数
- 临时措施：过期条件、失效规则、升级机制
- 隔离范围：维度有效性、规则完整性

**使用示例**：
```python
from src.validators.phase3a_validator import SchemaValidator

validator = SchemaValidator()
result = validator.validate_graph(workflow_graph)

if not result['valid']:
    for error in result['errors']:
        print(f"❌ {error['field']}: {error['message']}")
```

### 功能 2：LLM 采集（Collection Pipeline）

用于从专家的自然语言描述中提取结构化的 Phase 3-A 数据。

**采集问题**（20+ 个）：
- P1-P4：权限分级（4 个问题）
- A1-A4：聚合条件（4 个问题）
- T1-T4：临时措施（4 个问题）
- R1-R4：隔离范围（4 个问题）
- E1-E2：异常处理（2 个补充问题）

**使用示例**：
```python
from src.collection.phase3a_llm_prompts import Phase3ACollectionPipeline

pipeline = Phase3ACollectionPipeline()
plan = pipeline.create_collection_plan('李工程师', 'Release 批准流程')

# 执行 5 个阶段的采集
for phase in plan['phases']:
    print(f"Phase {phase['phase']}: {phase['estimated_time_minutes']}分钟")
    for question in phase['questions']:
        print(f"  {question.id}: {question.text}")
```

### 功能 3：交互式原型（HTML UI）

展示 4 个新维度在用户界面中的呈现方式。

**包含示例**：
- **n2**：聚合条件（趋势图表）
- **n3**：权限矩阵（3 角色顺序批准）
- **n5**：临时措施（72h OR 3-lot 倒计时）
- **n6**：隔离范围（equipment_id 维度）

---

## 🧪 测试覆盖

### 测试统计
- **总计**：24 个测试用例
- **通过率**：100% ✅
- **耗时**：< 5ms

### 覆盖范围

| 规则 | 测试数 | 覆盖 |
|---|---|---|
| 权限矩阵 | 6 | 有效、缺少字段、无效角色、无效顺序、重复、缺少标准 |
| 聚合条件 | 5 | 有效、无效方法、无效窗口、逻辑错误、缺少描述 |
| 临时措施 | 5 | 有效、无效格式、缺少字段、无效类型、缺少天数 |
| 隔离范围 | 5 | 有效、无效维度、缺少字段、类型错误 |
| 高级功能 | 3 | 完整 DAG、包含错误、摘要生成 |

---

## 📊 数据结构示例

### 权限矩阵

```json
{
  "approval_matrix": [
    {
      "approval_type": "equipment_release",
      "required_roles": ["equipment_engineer"],
      "sequence": "sequential",
      "criteria": "设备状态正常，无报警",
      "escalation_level": 1
    }
  ]
}
```

### 聚合条件

```json
{
  "aggregation": {
    "method": "trend",
    "window_size": 7,
    "operator": "all_increasing",
    "threshold": "0.5%",
    "min_samples": 5,
    "description": "过去 7 个批次持续上升"
  }
}
```

### 临时措施

```json
{
  "is_temporary": true,
  "expiration": {
    "duration": "PT72H",
    "lot_count": 3,
    "expiration_trigger": "duration_or_count"
  },
  "revocation_trigger": {
    "type": "reoccurrence",
    "days": 30
  }
}
```

### 隔离范围

```json
{
  "containment_scope": {
    "dimension": "equipment_id",
    "rule": "all_products_on_same_equipment",
    "applicable_conditions": ["equipment_failure"]
  }
}
```

---

## 🔄 集成步骤

### Step 1：导入模块

```python
from src.validators.phase3a_validator import SchemaValidator
from src.collection.phase3a_llm_prompts import Phase3ACollectionPipeline
```

### Step 2：在数据保存时验证

```python
def save_workflow_graph(graph_data):
    validator = SchemaValidator()
    result = validator.validate_graph(graph_data)
    
    if not result['valid']:
        raise ValidationError(f"数据验证失败：{result['summary']}")
    
    # 保存数据
    db.save(graph_data)
```

### Step 3：在采集流程中使用

```python
def collect_workflow(expert_name, workflow_name):
    pipeline = Phase3ACollectionPipeline()
    plan = pipeline.create_collection_plan(expert_name, workflow_name)
    
    for phase_info in plan['phases']:
        # 逐个提问
        for question in phase_info['questions']:
            user_answer = input(question.text)
            # 用 LLM 提取结构化数据
            extracted_data = llm.extract(question, user_answer)
    
    # 最后验证
    return validator.validate_graph(extracted_data)
```

---

## ⚠️ 已知限制

### 当前阶段（Phase 3-A）

1. **LLM 集成**
   - 采集模块只包含问题框架
   - 需要与 Claude API 或其他 LLM 集成以实现自动提取
   - 当前需要人工审核

2. **跨工作流规则**
   - Phase 3-A 关注单个工作流内的复杂性
   - 跨工作流的系统级规则属于 Phase 3-B

3. **性能**
   - 优化针对小到中等规模 DAG（< 100 节点）
   - 大规模 DAG 需要进一步优化

---

## 🗓️ 后续工作（Phase 3-B 及之后）

### 短期（1-2 周）
- [ ] 代码审查和反馈修复
- [ ] 集成到主应用代码库
- [ ] 采集团队培训

### 中期（3-4 周）
- [ ] LLM API 集成（Claude）
- [ ] 真实工作流样本验证
- [ ] 性能测试和优化

### 长期（1-2 个月）
- [ ] 系统级规则支持（Phase 3-B）
- [ ] 可视化增强（高级图表）
- [ ] 大规模 DAG 支持

---

## 📞 支持

### 文档
- **实现报告**：`PHASE3A_IMPLEMENTATION_COMPLETE.md`
- **使用示例**：`examples/phase3a_usage_examples.py`
- **API 文档**：代码注释和 docstring

### 常见问题

**Q: 如何运行测试？**
```bash
python -m unittest src.validators.test_phase3a_validator -v
```

**Q: 如何验证我的数据？**
```python
validator = SchemaValidator()
result = validator.validate_graph(my_graph)
print(result['summary'])
```

**Q: HTML 原型如何加载实际数据？**

参见 `PHASE3A_HTML_IMPLEMENTATION_GUIDE.md` 中的数据结构示例。

---

## 📈 预期成果

### 采集效率提升
- 采集时间：+1-2h（信息更完整）
- 采集质量：从 60% → 85% (+25%)
- 数据验证：从 40% → 95% (+55%)

### 系统覆盖率提升
- 权限管理：30% → 85%
- 聚合条件：20% → 90%
- 临时措施：15% → 85%
- 多维隔离：25% → 80%
- **整体**：35-40% → 65-75%

---

## 📋 检查清单

### 代码质量
- [x] 所有 24 个测试通过
- [x] 代码注释完整
- [x] 错误处理完善
- [x] 遵循 Python 最佳实践

### 文档完整性
- [x] 实现完成报告
- [x] 使用示例代码
- [x] 集成指南
- [x] 数据结构示例
- [x] 本 README

### 可用性
- [x] HTML 原型可交互
- [x] 示例代码可运行
- [x] 文档清晰易懂
- [x] 集成步骤明确

---

## 🎓 关键学习

### 设计原则

1. **最小化侵入性**：所有新字段为可选，完全向后兼容
2. **结构化表示**：复杂概念用嵌套对象表示
3. **渐进呈现**：主图显示摘要，详情留给面板
4. **采集友好**：字段名称与采集提示词对齐

### 技术亮点

1. **完整的验证框架**：支持级联验证和跨字段逻辑检查
2. **灵活的 LLM 集成**：模块化问题设计，易于扩展
3. **生产级原型**：高性能 SVG 渲染，完整交互

---

## 📝 版本信息

| 版本 | 日期 | 状态 | 说明 |
|---|---|---|---|
| 1.0 | 2026-10-07 | ✅ 完成 | 初始实现，核心功能完成 |

---

**最后更新**：2026-10-07  
**维护者**：Claude Haiku 4.5  
**分支**：`claude/sleepy-mendel-sllgin`

---

## 🙏 致谢

感谢采集团队的需求反馈和真实工作流案例，使得 Phase 3-A 设计更加贴近实际需求。
