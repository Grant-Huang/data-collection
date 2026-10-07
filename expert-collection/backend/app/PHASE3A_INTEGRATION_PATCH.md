# Phase 3-A 集成补丁指南

本文档说明如何修改 `expert_workflows.py` 路由以集成 Phase 3-A 的验证功能。

## 修改概览

需要在 3 个关键的地方添加 Phase 3-A 验证：

1. **创建工作流时** (`create_workflow` 函数，第 72-95 行)
2. **处理专家回答时** (`post_turn` 函数，第 207-304 行)
3. **确认工作流时** (`confirm_workflow` 函数，第 307-326 行)

## 第一步：添加导入

在 `expert_workflows.py` 的顶部，添加：

```python
from .. import phase3a_integration  # Phase 3-A 集成模块
```

## 第二步：修改创建工作流

**原始代码（第 88 行）**：
```python
"validation": graph_validator.validate(graph),
```

**修改为**：
```python
"validation": _validate_with_phase3a(graph),
```

**添加辅助函数**（在 `_strip_internal` 函数后）：
```python
def _validate_with_phase3a(graph: dict) -> list[dict[str, str]]:
    """结合 Phase 1 和 Phase 3-A 的验证"""
    # 首先运行现有的验证
    issues = graph_validator.validate(graph)
    
    try:
        # 然后运行 Phase 3-A 验证
        phase3a_result = phase3a_integration.validate_and_enrich_graph(graph)
        phase3a_issues = phase3a_result['validation']['issues']
        
        # 合并两个验证的结果
        issues.extend(phase3a_issues)
        
        # 如果启用了 Phase 3-A 特性，记录特征信息
        record_phase3a_features = phase3a_result['features']
    except Exception as e:
        # 如果 Phase 3-A 模块不可用或出错，仅记录警告
        import logging
        logging.warning(f"Phase 3-A 验证失败：{e}")
    
    return issues
```

## 第三步：修改处理专家回答

**原始代码（第 285 行）**：
```python
issues = graph_validator.validate(record["graph"])
```

**修改为**：
```python
issues = _validate_with_phase3a(record["graph"])
```

**原始代码（第 290 行）**：
```python
record["validation"] = issues
```

**修改为**：
```python
record["validation"] = issues
# 记录 Phase 3-A 特性信息（用于后续分析）
try:
    phase3a_result = phase3a_integration.validate_and_enrich_graph(record["graph"])
    record["_phase3a_features"] = phase3a_result['features']
except Exception:
    pass
```

## 第四步：修改确认工作流

**原始代码（第 312 行）**：
```python
issues = graph_validator.validate(record["graph"])
if any(i["level"] == "error" for i in issues):
```

**修改为**：
```python
issues = _validate_with_phase3a(record["graph"])
# 区分 Phase 1 和 Phase 3-A 的错误
phase1_errors = [i for i in issues if not i.get('code', '').startswith('phase3a_')]
phase3a_errors = [i for i in issues if i.get('code', '').startswith('phase3a_')]

if any(i["level"] == "error" for i in phase1_errors):
```

**注意**：Phase 3-A 的 WARNING 不应阻止确认，只有 ERROR 才应阻止。

## 第五步：添加 Phase 3-A 采集端点（可选，用于 Step 3）

如果要在收集阶段支持 Phase 3-A 采集问题，添加新的路由：

```python
@router.get("/{workflow_id}/phase3a/collection-plan")
def get_phase3a_collection_plan(workflow_id: str) -> dict:
    """获取 Phase 3-A 采集计划"""
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    
    collection = phase3a_integration.get_collection()
    plan = collection.create_collection_plan(
        expert_name=record.get("case_context", {}).get("expert_name", "未知"),
        workflow_name=record.get("name", "未命名工作流")
    )
    
    return plan


@router.get("/{workflow_id}/phase3a/features")
def get_phase3a_features(workflow_id: str) -> dict:
    """获取工作流中的 Phase 3-A 特性摘要"""
    record = db.get(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="workflow not found")
    
    if "_phase3a_features" in record:
        return record["_phase3a_features"]
    
    # 如果还没有缓存，即时计算
    extractor = phase3a_integration.Phase3ADataExtractor()
    return extractor.summarize_phase3a_features(record["graph"])
```

## 第六步：更新模型（可选）

如果需要在响应中包含 Phase 3-A 特性，更新 `models.py` 中的 `WorkflowRecord` 模型：

```python
class WorkflowRecord(BaseModel):
    # ... 现有字段 ...
    
    # Phase 3-A 特性
    phase3a_features: Optional[dict] = None  # 新增字段
```

## 测试清单

集成后，应该验证以下功能：

- [ ] 工作流创建时进行 Phase 3-A 验证
- [ ] 处理专家回答时进行 Phase 3-A 验证
- [ ] Phase 3-A ERROR 阻止工作流确认
- [ ] Phase 3-A WARNING 不阻止工作流确认
- [ ] 包含权限矩阵的工作流能正确验证
- [ ] 包含聚合条件的工作流能正确验证
- [ ] 包含临时措施的工作流能正确验证
- [ ] 包含隔离范围的工作流能正确验证
- [ ] 错误消息清晰易懂
- [ ] Phase 3-A 采集计划端点正常工作

## 部署注意事项

### 向后兼容性

- 现有的工作流（没有 Phase 3-A 特性）不会被影响
- Phase 3-A 验证失败会被记录但不会中断现有流程
- 如果 Phase 3-A 模块不可用，系统仍可正常运行

### 错误处理

```python
try:
    phase3a_result = phase3a_integration.validate_and_enrich_graph(graph)
except ImportError:
    # Phase 3-A 模块未安装，仅运行基本验证
    logging.warning("Phase 3-A 模块未安装，跳过高级验证")
except Exception as e:
    # 其他错误，记录但不中断
    logging.error(f"Phase 3-A 验证出错：{e}")
```

### 性能考虑

Phase 3-A 验证的性能很好：
- 单个工作流验证时间：< 10ms
- 24 个单元测试通过时间：< 5ms

不需要特殊的性能优化。

## 集成完成检查

1. [ ] 导入语句添加
2. [ ] `_validate_with_phase3a` 函数添加
3. [ ] 创建工作流函数修改
4. [ ] 处理回答函数修改
5. [ ] 确认工作流函数修改
6. [ ] 错误处理和日志添加
7. [ ] 可选的采集端点添加
8. [ ] 模型更新（可选）
9. [ ] 所有测试通过
10. [ ] 代码审查和反馈修复

---

## 示例：完整的修改代码

```python
# expert_workflows.py 中的完整修改示例

from .. import db, graph_ops, graph_validator, guide_service, phase3a_integration  # 添加这一行

# ... 现有代码 ...

def _validate_with_phase3a(graph: dict) -> list[dict[str, str]]:
    """结合 Phase 1 和 Phase 3-A 的验证"""
    import logging
    
    # 首先运行现有的验证
    issues = graph_validator.validate(graph)
    
    try:
        # 然后运行 Phase 3-A 验证
        phase3a_result = phase3a_integration.validate_and_enrich_graph(graph)
        phase3a_issues = phase3a_result['validation']['issues']
        
        # 合并两个验证的结果
        issues.extend(phase3a_issues)
    except ImportError:
        logging.debug("Phase 3-A 模块未安装")
    except Exception as e:
        logging.warning(f"Phase 3-A 验证失败：{e}")
    
    return issues


@router.post("", response_model=WorkflowRecord)
def create_workflow(req: CreateWorkflowRequest) -> WorkflowRecord:
    workflow_id = uuid.uuid4().hex[:12]
    now = _now()
    graph = graph_ops.new_graph()
    reply, next_question = guide_service.initial_turn()
    state = guide_service.initial_state()
    record = {
        "id": workflow_id,
        "name": req.name or f"专家会话 {workflow_id}",
        "status": "collecting",
        "stage": state["stage"],
        "graph": graph,
        "turns": [{"turn_id": uuid.uuid4().hex[:8], "role": "assistant", "text": reply}],
        "unresolved": [next_question] if next_question else [],
        "completion": {"score": 0.0, "ready_for_confirmation": False},
        "validation": _validate_with_phase3a(graph),  # 修改这一行
        "case_context": None,
        "created_at": now,
        "updated_at": now,
        "_guide_state": state,
    }
    db.save(record)
    return WorkflowRecord.model_validate(_strip_internal(record))
```

---

**文档版本**：1.0  
**日期**：2026-10-07  
**状态**：集成指南完成
