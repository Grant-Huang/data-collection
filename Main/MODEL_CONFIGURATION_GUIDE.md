# 🎯 多模型分层架构配置指南

## 📊 架构概览

本项目采用**三层模型分层架构**，根据任务复杂度和数据隐私需求自动选择最优模型：

```
┌─────────────────────────────────────────────────────────┐
│           多模型分层架构 (Multi-Tier Model Stack)       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  任务类型        模型配置              特点             │
│  ────────────────────────────────────────────────────  │
│  小型 JSON       本地 7B/8B (L)    快速、零成本        │
│  (聚类、脱敏)    独立推理          隐私优先            │
│                                                          │
│  复杂工作流      本地 27B/35B      支持thinking       │
│  (流程提取、      (C_standard)      数据隐私           │
│   图重生成)       推理不联网        离线部署           │
│                                                          │
│  长文本分析      云端 DeepSeek     1M context         │
│  (实验解读、      Flash             高质量输出         │
│   Dashboard)     (C_flagship)       成本低 (~$0.14)    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 🔧 环境配置

### 1️⃣ 模型配置类 (ModelConfig)

```python
from model_config import ModelTier, ModelRegistry, ModelConfig

# 查看所有可用模型
for model in ModelRegistry.list_all_models():
    print(f"{model.name}: {model.model_id}")

# 根据任务类型获取模型
from model_config import TaskType
model = ModelRegistry.get_model_for_task(TaskType.FLOW_EXTRACTION)
print(model)
# Output: ModelConfig(
#   tier=ModelTier.LOCAL_STANDARD,
#   name='Local 27B/35B',
#   model_id='local-27b-35b',
#   max_tokens=8192,
#   supports_thinking=True,
#   context_length=32768,
#   is_local=True,
#   cost_per_1m_tokens=0.0
# )
```

### 2️⃣ 模型选择器 (ModelSelector)

根据具体情况智能选择模型：

```python
from model_config import ModelSelector

# 为DAG生成选择模型（隐私优先）
model = ModelSelector.select_for_dag_generation(
    input_length=50000,
    require_privacy=True,
    require_thinking=True
)
# → 自动选择: Local 27B/35B

# 为访谈模拟选择模型
model = ModelSelector.select_for_interview(input_length=100000)
# → 自动选择: Local 27B/35B

# 为质量验证选择模型
model = ModelSelector.select_for_validation(num_nodes=20, num_edges=25)
# → 自动选择: Local 7B/8B（简单验证）
```

## 🏗️ ABC 抽象基类架构

### 处理器基类 (WorkflowProcessor)

所有工作流处理器都继承自 `WorkflowProcessor` 抽象基类：

```python
from model_config import WorkflowProcessor, ModelConfig

class CustomProcessor(WorkflowProcessor):
    def __init__(self, model_config: Optional[ModelConfig] = None):
        super().__init__(model_config)
    
    def process(self, input_data: Any) -> Any:
        """处理输入数据"""
        # 自动选择模型（如果未指定）
        if self.model_config is None:
            # 自动选择逻辑
            pass
        
        # 处理数据
        result = self._do_processing(input_data)
        return result
    
    def validate(self, output_data: Any) -> bool:
        """验证输出数据"""
        return True
    
    def _do_processing(self, data):
        """实现具体的处理逻辑"""
        pass

# 使用示例
processor = CustomProcessor()
result = processor.process({"key": "value"})
print(processor.get_model_info())
```

### 三个核心处理器

#### 1. InterviewProcessor（访谈处理器）
```python
from model_config import InterviewProcessor

processor = InterviewProcessor()
result = processor.process({
    "conversation": "质量工程师：我们遇到了尺寸超差的问题..."
})
# 自动选择: Local 27B/35B
# 用于处理专家访谈数据
```

#### 2. DAGGenerator（DAG生成器）
```python
from model_config import DAGGenerator

generator = DAGGenerator()
dag_output = generator.process({
    "nodes": [...],
    "edges": [...]
})
# 自动选择: Local 27B/35B（隐私优先）
# 从流程数据生成结构化DAG
```

#### 3. WorkflowValidator（工作流验证器）
```python
from model_config import WorkflowValidator

validator = WorkflowValidator()
validation_result = validator.process({
    "nodes": [...],
    "edges": [...]
})
# 自动选择: Local 7B/8B 或 Local 27B/35B（取决于复杂度）
# 验证工作流数据完整性
```

## 📋 任务类型映射表

| 任务类型 | 模型选择 | 适用场景 | 特点 |
|---------|---------|---------|------|
| **CLUSTERING** | 本地 7B/8B | 数据聚类 | 快速、轻量 |
| **ANONYMIZATION** | 本地 7B/8B | 数据脱敏 | 无网络依赖 |
| **SIMPLE_JSON** | 本地 7B/8B | 生成简单JSON | 低成本 |
| **FLOW_EXTRACTION** | 本地 27B/35B | 流程提取 | 支持思考 |
| **GRAPH_GENERATION** | 本地 27B/35B | 图重生成 | 数据隐私 |
| **COMPLEX_THINKING** | 本地 27B/35B | 深度推理 | 本地部署 |
| **EXPLANATION** | 云端DeepSeek | 详细分析 | 高质量 |
| **DASHBOARD** | 云端DeepSeek | 生成报告 | 1M上下文 |
| **PROSE_GENERATION** | 云端DeepSeek | 长文本生成 | 成本低 |

## 🚀 在DAG项目中集成

### 示例 1：集成到现有的 e2e_expert_dag_workflow_test.py

```python
from model_config import (
    DAGGenerator, InterviewProcessor, WorkflowValidator,
    ModelRegistry, TaskType
)

class EnhancedExpertInterviewSimulator:
    def __init__(self):
        self.interview_processor = InterviewProcessor()
        self.dag_generator = DAGGenerator()
        self.workflow_validator = WorkflowValidator()
    
    def run_with_model_selection(self):
        # 步骤 1：处理访谈（自动选择最优模型）
        interview_data = self.simulate_interview()
        processed = self.interview_processor.process(interview_data)
        print(f"使用模型: {self.interview_processor.get_model_info()}")
        
        # 步骤 2：生成DAG（自动选择最优模型）
        dag_output = self.dag_generator.process(processed)
        print(f"使用模型: {self.dag_generator.get_model_info()}")
        
        # 步骤 3：验证（自动选择最优模型）
        validation_result = self.workflow_validator.process(dag_output)
        print(f"使用模型: {self.workflow_validator.get_model_info()}")
```

### 示例 2：指定特定模型

```python
from model_config import DAGGenerator, ModelRegistry, ModelTier

# 明确指定使用云端模型（用于详细分析）
flagship_model = ModelRegistry.get_model_by_tier(ModelTier.CLOUD_FLAGSHIP)
generator = DAGGenerator(model_config=flagship_model)

result = generator.process(workflow_data)
```

### 示例 3：配置管理器

```python
from model_config import ConfigManager, ModelTier

config = ConfigManager()

# 为特定任务设置模型
config.set_task_model_tier("quality_analysis", ModelTier.LOCAL_STANDARD)
config.set_task_model_tier("visualization", ModelTier.CLOUD_FLAGSHIP)

# 打印配置状态
config.print_model_status()
```

## 💡 最佳实践

### 1️⃣ 隐私优先原则
```python
# ✅ 推荐：使用本地模型处理敏感数据
generator = DAGGenerator()  # 自动选择本地模型
result = generator.process(sensitive_workflow_data)

# ❌ 避免：未经明确同意不要将敏感数据发送到云端
```

### 2️⃣ 成本优化
```python
# ✅ 推荐：按任务复杂度选择模型
processor = InterviewProcessor()  # 自动选择合适的模型

# ❌ 避免：所有任务都用云端最强模型
```

### 3️⃣ 性能平衡
```python
# ✅ 推荐：大数据量用本地模型，需要高质量输出时用云端
if len(data) > 100000:
    model = ModelSelector.select_for_dag_generation(
        input_length=len(data),
        require_privacy=True
    )
else:
    model = ModelRegistry.get_model_for_task(TaskType.EXPLANATION)

# ❌ 避免：忽视数据量和任务复杂度
```

## 📈 模型性能对比

```
任务: DAG图生成 (10个节点, 15条边)
─────────────────────────────────────────
模型                  延迟    成本      质量
─────────────────────────────────────────
本地 7B/8B          ~500ms   $0      ⭐⭐⭐
本地 27B/35B        ~2s      $0      ⭐⭐⭐⭐
DeepSeek Flash      ~1.5s    $0.001  ⭐⭐⭐⭐⭐
─────────────────────────────────────────

任务: 长文本分析 (50KB+ 报告)
─────────────────────────────────────────
模型                  延迟    成本      质量
─────────────────────────────────────────
本地 27B/35B        ~5s      $0      ⭐⭐⭐
DeepSeek Flash      ~2s      $0.05   ⭐⭐⭐⭐⭐
─────────────────────────────────────────
```

## 🔍 调试和诊断

### 查看模型状态
```python
from model_config import ModelRegistry

# 打印所有模型
for model in ModelRegistry.list_all_models():
    print(f"{model.name}")
    print(f"  Context: {model.context_length:,} tokens")
    print(f"  Thinking: {model.supports_thinking}")
    print(f"  Location: {'Local' if model.is_local else 'Cloud'}")
```

### 获取处理器的模型信息
```python
processor = DAGGenerator()
processor.process(data)

model_info = processor.get_model_info()
print(model_info)
# Output:
# {
#     'tier': 'local_27b_35b',
#     'name': 'Local 27B/35B',
#     'model_id': 'local-27b-35b',
#     'is_local': True,
#     'context_length': 32768,
#     'supports_thinking': True
# }
```

## 📚 参考文档

- `model_config.py` - 完整的模型配置实现
- `e2e_expert_dag_workflow_test.py` - DAG生成测试脚本
- `generated_workflow_dags.json` - DAG生成结果示例

## 🎓 下一步

1. ✅ 将 `model_config.py` 集成到 `e2e_expert_dag_workflow_test.py`
2. ✅ 为每个处理阶段选择最优模型
3. ✅ 添加模型使用日志和成本追踪
4. ✅ 支持运行时动态模型切换
