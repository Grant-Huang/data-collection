#!/usr/bin/env python3
"""
多模型分层架构配置管理
支持本地和云端模型的自适应选择
"""

import json
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


class ModelTier(Enum):
    """模型层级"""
    LOCAL_SMALL = "local_7b_8b"          # 本地轻量级 (L)
    LOCAL_STANDARD = "local_27b_35b"     # 本地标准 (C_standard)
    CLOUD_FLAGSHIP = "cloud_deepseek"    # 云端旗舰 (C_flagship)


class TaskType(Enum):
    """任务类型"""
    # 小型任务 - 使用 LOCAL_SMALL (7B/8B)
    CLUSTERING = "clustering"             # 聚类
    ANONYMIZATION = "anonymization"       # 脱敏
    SIMPLE_JSON = "simple_json"          # 简单JSON生成

    # 复杂任务 - 使用 LOCAL_STANDARD (27B/35B)
    FLOW_EXTRACTION = "flow_extraction"   # 流程提取
    GRAPH_GENERATION = "graph_generation" # 图重生成
    COMPLEX_THINKING = "complex_thinking" # 需要深度思考的任务

    # 长文本理解 - 使用 CLOUD_FLAGSHIP
    EXPLANATION = "explanation"           # 实验解读、深度分析
    DASHBOARD = "dashboard"               # Dashboard生成
    PROSE_GENERATION = "prose_generation" # 长文本生成


@dataclass
class ModelConfig:
    """单个模型配置"""
    tier: ModelTier
    name: str
    model_id: str
    max_tokens: int
    supports_thinking: bool
    context_length: int
    is_local: bool
    cost_per_1m_tokens: float  # 单位：美元


class ModelRegistry:
    """模型注册表"""

    MODELS: Dict[ModelTier, ModelConfig] = {
        ModelTier.LOCAL_SMALL: ModelConfig(
            tier=ModelTier.LOCAL_SMALL,
            name="Local 7B/8B",
            model_id="local-7b-8b",
            max_tokens=4096,
            supports_thinking=False,
            context_length=8192,
            is_local=True,
            cost_per_1m_tokens=0.0  # 本地无成本
        ),
        ModelTier.LOCAL_STANDARD: ModelConfig(
            tier=ModelTier.LOCAL_STANDARD,
            name="Local 27B/35B",
            model_id="local-27b-35b",
            max_tokens=8192,
            supports_thinking=True,
            context_length=32768,
            is_local=True,
            cost_per_1m_tokens=0.0  # 本地无成本
        ),
        ModelTier.CLOUD_FLAGSHIP: ModelConfig(
            tier=ModelTier.CLOUD_FLAGSHIP,
            name="DeepSeek Flash",
            model_id="deepseek-flash",
            max_tokens=16384,
            supports_thinking=True,
            context_length=1000000,  # 1M tokens
            is_local=False,
            cost_per_1m_tokens=0.14  # 约 $0.14 per 1M
        ),
    }

    # 任务类型到模型层级的映射
    TASK_TO_TIER: Dict[TaskType, ModelTier] = {
        # 小型任务
        TaskType.CLUSTERING: ModelTier.LOCAL_SMALL,
        TaskType.ANONYMIZATION: ModelTier.LOCAL_SMALL,
        TaskType.SIMPLE_JSON: ModelTier.LOCAL_SMALL,

        # 复杂任务
        TaskType.FLOW_EXTRACTION: ModelTier.LOCAL_STANDARD,
        TaskType.GRAPH_GENERATION: ModelTier.LOCAL_STANDARD,
        TaskType.COMPLEX_THINKING: ModelTier.LOCAL_STANDARD,

        # 长文本处理
        TaskType.EXPLANATION: ModelTier.CLOUD_FLAGSHIP,
        TaskType.DASHBOARD: ModelTier.CLOUD_FLAGSHIP,
        TaskType.PROSE_GENERATION: ModelTier.CLOUD_FLAGSHIP,
    }

    @classmethod
    def get_model_for_task(cls, task_type: TaskType) -> ModelConfig:
        """根据任务类型获取合适的模型"""
        tier = cls.TASK_TO_TIER.get(task_type)
        if tier is None:
            raise ValueError(f"Unknown task type: {task_type}")
        return cls.MODELS[tier]

    @classmethod
    def get_model_by_tier(cls, tier: ModelTier) -> ModelConfig:
        """根据模型层级获取配置"""
        return cls.MODELS[tier]

    @classmethod
    def list_all_models(cls) -> List[ModelConfig]:
        """列出所有模型"""
        return list(cls.MODELS.values())


class ModelSelector:
    """模型选择器 - 根据上下文智能选择模型"""

    @staticmethod
    def select_for_dag_generation(
        input_length: int,
        require_privacy: bool = True,
        require_thinking: bool = False
    ) -> ModelConfig:
        """
        为DAG生成选择最优模型

        Args:
            input_length: 输入长度（字符数）
            require_privacy: 是否要求数据隐私（使用本地模型）
            require_thinking: 是否需要深度推理

        Returns:
            ModelConfig: 选择的模型配置
        """
        # DAG生成属于复杂任务
        if require_privacy or input_length < 100000:
            # 优先使用本地模型（隐私优先或数据量不大）
            return ModelRegistry.get_model_for_task(TaskType.GRAPH_GENERATION)
        else:
            # 数据量大且不需要隐私保护，用云端模型
            return ModelRegistry.get_model_for_task(TaskType.EXPLANATION)

    @staticmethod
    def select_for_interview(input_length: int) -> ModelConfig:
        """为访谈模拟选择模型"""
        if input_length < 50000:
            return ModelRegistry.get_model_for_task(TaskType.FLOW_EXTRACTION)
        else:
            return ModelRegistry.get_model_for_task(TaskType.COMPLEX_THINKING)

    @staticmethod
    def select_for_validation(num_nodes: int, num_edges: int) -> ModelConfig:
        """为质量验证选择模型"""
        # 验证是简单任务
        if num_nodes < 50 and num_edges < 100:
            return ModelRegistry.get_model_for_task(TaskType.SIMPLE_JSON)
        else:
            return ModelRegistry.get_model_for_task(TaskType.COMPLEX_THINKING)


# ============================================================================
# ABC 抽象基类架构
# ============================================================================

class WorkflowProcessor(ABC):
    """工作流处理的抽象基类"""

    def __init__(self, model_config: Optional[ModelConfig] = None):
        """
        初始化处理器

        Args:
            model_config: 模型配置，如果为None则自动选择
        """
        self.model_config = model_config

    @abstractmethod
    def process(self, input_data: Any) -> Any:
        """处理输入数据"""
        pass

    @abstractmethod
    def validate(self, output_data: Any) -> bool:
        """验证输出数据"""
        pass

    def get_model_info(self) -> Dict[str, Any]:
        """获取使用的模型信息"""
        if self.model_config is None:
            return {"status": "model_not_configured"}

        return {
            "tier": self.model_config.tier.value,
            "name": self.model_config.name,
            "model_id": self.model_config.model_id,
            "is_local": self.model_config.is_local,
            "context_length": self.model_config.context_length,
            "supports_thinking": self.model_config.supports_thinking,
        }


class InterviewProcessor(WorkflowProcessor):
    """访谈处理器"""

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理访谈数据"""
        # 自动选择模型
        if self.model_config is None:
            interview_text = input_data.get("conversation", "")
            self.model_config = ModelSelector.select_for_interview(len(interview_text))

        # TODO: 实现实际的访谈处理逻辑
        return {"status": "processed", "model_used": self.model_config.name}

    def validate(self, output_data: Any) -> bool:
        """验证访谈输出"""
        return isinstance(output_data, dict) and "conversation" in output_data


class DAGGenerator(WorkflowProcessor):
    """DAG生成器"""

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """从流程数据生成DAG"""
        # 自动选择模型
        if self.model_config is None:
            flow_data = json.dumps(input_data)
            self.model_config = ModelSelector.select_for_dag_generation(
                input_length=len(flow_data),
                require_privacy=True,
                require_thinking=True
            )

        # TODO: 实现实际的DAG生成逻辑
        return {"status": "generated", "model_used": self.model_config.name}

    def validate(self, output_data: Any) -> bool:
        """验证DAG输出"""
        if not isinstance(output_data, dict):
            return False
        return "nodes" in output_data and "edges" in output_data


class WorkflowValidator(WorkflowProcessor):
    """工作流验证器"""

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证工作流数据"""
        # 自动选择模型
        if self.model_config is None:
            num_nodes = len(input_data.get("nodes", []))
            num_edges = len(input_data.get("edges", []))
            self.model_config = ModelSelector.select_for_validation(num_nodes, num_edges)

        # TODO: 实现实际的验证逻辑
        return {"status": "validated", "model_used": self.model_config.name}

    def validate(self, output_data: Any) -> bool:
        """验证验证结果"""
        return isinstance(output_data, dict) and "status" in output_data


# ============================================================================
# 配置管理器
# ============================================================================

class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self.model_registry = ModelRegistry()
        self.task_configs: Dict[str, ModelTier] = {}

    def set_task_model_tier(self, task_name: str, tier: ModelTier):
        """为特定任务设置模型层级"""
        self.task_configs[task_name] = tier

    def get_model_for_task_name(self, task_name: str) -> ModelConfig:
        """根据任务名称获取模型"""
        if task_name in self.task_configs:
            tier = self.task_configs[task_name]
            return self.model_registry.get_model_by_tier(tier)
        else:
            raise ValueError(f"Task {task_name} not configured")

    def print_model_status(self):
        """打印模型状态信息"""
        print("\n" + "="*80)
        print("📊 多模型分层架构配置")
        print("="*80)
        for model in self.model_registry.list_all_models():
            print(f"\n🔷 {model.name} ({model.tier.value})")
            print(f"   Model ID: {model.model_id}")
            print(f"   Max Tokens: {model.max_tokens}")
            print(f"   Context: {model.context_length:,} tokens")
            print(f"   Thinking: {'✅' if model.supports_thinking else '❌'}")
            print(f"   Location: {'本地' if model.is_local else '云端'}")
            if not model.is_local:
                print(f"   Cost: ${model.cost_per_1m_tokens}/1M tokens")


if __name__ == "__main__":
    # 示例使用
    manager = ConfigManager()
    manager.print_model_status()

    # 示例：选择模型
    print("\n" + "="*80)
    print("📋 任务类型 → 模型映射")
    print("="*80)
    for task_type in TaskType:
        model = ModelRegistry.get_model_for_task(task_type)
        print(f"{task_type.value:30} → {model.name:20} ({model.tier.value})")

    # 示例：使用处理器
    print("\n" + "="*80)
    print("🔄 处理器示例")
    print("="*80)

    dag_gen = DAGGenerator()
    result = dag_gen.process({"nodes": [], "edges": []})
    print(f"DAG生成器: {result}")
    print(f"模型信息: {dag_gen.get_model_info()}")
