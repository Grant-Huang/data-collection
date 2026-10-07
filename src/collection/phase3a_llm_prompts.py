"""Phase 3-A LLM 采集提示词集成模块

此模块提供专家工作流采集的问题集和 LLM 交互逻辑，
用于从专家的自然语言描述中提取 Phase 3-A 新维度的结构化数据。
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


class QuestionCategory(str, Enum):
    """问题分类"""
    PERMISSION_HIERARCHY = "permission_hierarchy"  # 权限分级和多层签字
    AGGREGATION_CONDITIONS = "aggregation_conditions"  # 聚合和趋势条件
    TEMPORARY_MEASURES = "temporary_measures"  # 临时措施生命周期
    TRACEABILITY = "traceability"  # 多维追溯和隔离范围
    EXCEPTION_HANDLING = "exception_handling"  # 异常处理补充


@dataclass
class LLMQuestion:
    """LLM 采集的单个问题"""
    id: str  # 问题唯一标识
    category: QuestionCategory  # 问题分类
    text: str  # 问题文本
    context: str  # 背景说明
    example: Optional[str] = None  # 示例回答
    follow_up: Optional[List[str]] = None  # 后续问题模板

    def to_prompt(self) -> str:
        """转换为 LLM 提示词格式"""
        prompt = f"问题 [{self.id}]：{self.text}\n"
        if self.context:
            prompt += f"背景：{self.context}\n"
        if self.example:
            prompt += f"示例：{self.example}\n"
        return prompt


class Phase3AQuestionSet:
    """Phase 3-A 采集问题集"""

    def __init__(self):
        """初始化问题集"""
        self.questions: Dict[QuestionCategory, List[LLMQuestion]] = {}
        self._initialize_questions()

    def _initialize_questions(self) -> None:
        """初始化所有问题"""

        # 1. 权限分级和多层签字 (4 个问题)
        self.questions[QuestionCategory.PERMISSION_HIERARCHY] = [
            LLMQuestion(
                id="P1",
                category=QuestionCategory.PERMISSION_HIERARCHY,
                text="此流程中需要哪些角色的批准或签字？",
                context="了解有哪些不同的角色需要参与批准决策",
                example="设备工程师需要检查设备状态，工艺工程师需要检查工艺参数，质量工程师需要进行首件检验"
            ),
            LLMQuestion(
                id="P2",
                category=QuestionCategory.PERMISSION_HIERARCHY,
                text="这些批准是需要顺序进行（一个接一个）还是可以并行进行？",
                context="理解批准流程的顺序依赖关系",
                example="设备工程师先批准，再到工艺工程师，最后质量工程师；或者他们可以同时进行批准",
                follow_up=[
                    "如果顺序进行，为什么必须按这个顺序？",
                    "如果某个批准被拒绝，流程如何处理？"
                ]
            ),
            LLMQuestion(
                id="P3",
                category=QuestionCategory.PERMISSION_HIERARCHY,
                text="每个角色的具体批准标准是什么？他们如何判断是否可以批准？",
                context="获取每个角色的决策标准和条件",
                example="设备工程师检查：设备无报警、温度正常、压力在范围内；工艺工程师检查：刀具寿命充足、参数设置正确"
            ),
            LLMQuestion(
                id="P4",
                category=QuestionCategory.PERMISSION_HIERARCHY,
                text="如果某个人无法及时批准，流程是否会升级到更高级别？具体如何升级？",
                context="了解升级机制和处理延迟的策略",
                example="如果工艺工程师 2 小时内未批准，自动升级到生产主管；质量工程师延迟则升级到生产副总"
            )
        ]

        # 2. 聚合和趋势条件 (4 个问题)
        self.questions[QuestionCategory.AGGREGATION_CONDITIONS] = [
            LLMQuestion(
                id="A1",
                category=QuestionCategory.AGGREGATION_CONDITIONS,
                text="此流程是否需要观察单个数据点，还是需要查看一段时间内数据的趋势？",
                context="区分单点判断和趋势判断的需求",
                example="单点：检测这一次的温度是否超过 85°C；趋势：检测过去 7 次测量中温度是否持续上升"
            ),
            LLMQuestion(
                id="A2",
                category=QuestionCategory.AGGREGATION_CONDITIONS,
                text="如果需要看趋势，通常需要观察多少个历史数据点（或多长时间）？",
                context="确定聚合窗口的大小",
                example="最近 7 个生产批次的数据，或过去 24 小时内的测量记录"
            ),
            LLMQuestion(
                id="A3",
                category=QuestionCategory.AGGREGATION_CONDITIONS,
                text="对于这些趋势数据，需要检查什么样的模式或规则？",
                context="理解趋势判断的具体规则",
                example="缺陷数量持续增加（趋势上升），或者在特定时间段内缺陷数量有异常峰值"
            ),
            LLMQuestion(
                id="A4",
                category=QuestionCategory.AGGREGATION_CONDITIONS,
                text="这个规则需要多少个有效的数据点才能做出判断？",
                context="了解最小样本数的需求",
                example="至少需要 5 次完整的测量结果；或如果缺少数据，则不进行判断"
            )
        ]

        # 3. 临时措施和有效期限制 (4 个问题)
        self.questions[QuestionCategory.TEMPORARY_MEASURES] = [
            LLMQuestion(
                id="T1",
                category=QuestionCategory.TEMPORARY_MEASURES,
                text="此流程中是否有临时的绕过（bypass）或特殊处理措施？这些是什么？",
                context="识别临时措施和特殊情况处理",
                example="设备故障期间允许临时跳过某项检测，但仅限于 72 小时以内"
            ),
            LLMQuestion(
                id="T2",
                category=QuestionCategory.TEMPORARY_MEASURES,
                text="这些临时措施的有效期是多长？用什么方式衡量（时间、产品数量、其他）？",
                context="定义临时措施的过期条件",
                example="有效期 72 小时或 3 个 lot，先达到任一条件就自动失效；或最多使用 2 次，之后必须升级"
            ),
            LLMQuestion(
                id="T3",
                category=QuestionCategory.TEMPORARY_MEASURES,
                text="如果临时措施到期后，同样的问题再次出现，会如何处理？",
                context="了解临时措施失效后的处理机制",
                example="30 天内同一故障再次出现则自动停止所有 bypass，升级为完整的根因分析和 CAPA"
            ),
            LLMQuestion(
                id="T4",
                category=QuestionCategory.TEMPORARY_MEASURES,
                text="如果临时措施被反复使用，是否会触发某种升级或警告机制？",
                context="理解重复使用临时措施的处理",
                example="同一临时措施在 30 天内被使用超过 3 次，自动创建 CAPA 并分配给质量部门"
            )
        ]

        # 4. 多维追溯和隔离范围 (4 个问题)
        self.questions[QuestionCategory.TRACEABILITY] = [
            LLMQuestion(
                id="R1",
                category=QuestionCategory.TRACEABILITY,
                text="如果此流程中发现问题，需要隔离或追踪哪些受影响的产品或设备？",
                context="理解隔离的范围和维度",
                example="根据设备隔离：所有在该设备上加工的产品；根据原料隔离：所有使用该原料批次的产品"
            ),
            LLMQuestion(
                id="R2",
                category=QuestionCategory.TRACEABILITY,
                text="隔离范围是否会根据根本原因而改变？",
                context="了解隔离规则的条件依赖",
                example="如果是设备故障，隔离所有在该设备上的产品；如果是原料问题，隔离该原料批次的所有产品"
            ),
            LLMQuestion(
                id="R3",
                category=QuestionCategory.TRACEABILITY,
                text="通常需要隔离多少数量的产品？如何处理这些隔离的产品？",
                context="评估隔离的影响和处理方案",
                example="通常隔离 200-500 件产品，进行 100% 检验或报废"
            ),
            LLMQuestion(
                id="R4",
                category=QuestionCategory.TRACEABILITY,
                text="是否需要向下游（客户）通知这些隔离情况？通知流程是什么？",
                context="了解隔离信息的传播和沟通",
                example="如果隔离产品已发货，需要立即通知销售和客户服务部门"
            )
        ]

        # 5. 异常处理补充 (补充问题)
        self.questions[QuestionCategory.EXCEPTION_HANDLING] = [
            LLMQuestion(
                id="E1",
                category=QuestionCategory.EXCEPTION_HANDLING,
                text="此流程中还有其他特殊情况或例外处理吗？",
                context="捕获其他重要的异常情况",
                example="周末或假日加班时采用简化流程；新员工前 3 个月需要额外检查"
            ),
            LLMQuestion(
                id="E2",
                category=QuestionCategory.EXCEPTION_HANDLING,
                text="如果流程中出现数据不完整或不确定的情况，如何处理？",
                context="了解数据质量和完整性的处理",
                example="如果无法获得完整的设备温度历史，自动升级到人工审核"
            )
        ]

    def get_questions_by_category(self, category: QuestionCategory) -> List[LLMQuestion]:
        """按分类获取问题"""
        return self.questions.get(category, [])

    def get_all_questions(self) -> Dict[QuestionCategory, List[LLMQuestion]]:
        """获取所有问题"""
        return self.questions

    def get_questions_for_workflow(self, workflow_type: Optional[str] = None) -> List[LLMQuestion]:
        """
        根据工作流类型获取相关问题

        Args:
            workflow_type: 工作流类型（可选），如 'approval', 'quality', 'production'

        Returns:
            推荐的问题列表
        """
        # 默认返回所有分类的问题（可根据 workflow_type 定制）
        all_questions = []
        for questions_list in self.questions.values():
            all_questions.extend(questions_list)
        return all_questions


class LLMExtractionContext:
    """LLM 数据提取的上下文"""

    def __init__(self, expert_name: str, workflow_name: str):
        self.expert_name = expert_name
        self.workflow_name = workflow_name
        self.extracted_data = {}  # 提取的结构化数据
        self.conversation_history = []  # 对话历史

    def add_qa_pair(self, question: str, answer: str) -> None:
        """添加问答对到对话历史"""
        self.conversation_history.append({
            'role': 'user',
            'content': question
        })
        self.conversation_history.append({
            'role': 'assistant',
            'content': answer
        })

    def extract_approval_matrix(self, conversation: List[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
        """
        从对话中提取权限矩阵

        Args:
            conversation: 完整的问答对话

        Returns:
            提取的 approval_matrix 结构，或 None 如果无法提取
        """
        # 这应该由 LLM 实现，这里提供模板
        return None

    def extract_aggregation_conditions(self, conversation: List[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
        """从对话中提取聚合条件"""
        return None

    def extract_temporary_measures(self, conversation: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """从对话中提取临时措施"""
        return None

    def extract_containment_scope(self, conversation: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """从对话中提取隔离范围"""
        return None


class Phase3APromptTemplate:
    """Phase 3-A 采集的提示词模板"""

    SYSTEM_PROMPT = """你是一个工作流分析专家。你的任务是帮助从专家的描述中提取结构化的工作流信息。

对于提供的每个问题，请：
1. 仔细理解专家的回答
2. 识别关键信息（角色、条件、规则等）
3. 提取为结构化数据格式

如果某些信息不清楚或缺失，请在最后提出澄清问题。"""

    FIRST_ROUND_PROMPT = """我正在帮助 {expert_name} 记录他们关于"{workflow_name}"工作流的知识。

请逐个回答以下关于"{dimension}"的问题。对每个答案，请提供具体的细节和例子。

{questions}

请确保你的回答清晰、具体，包含实际的标准、条件或规则。"""

    SECOND_ROUND_PROMPT = """基于之前的对话，我有一些后续问题需要澄清：

{follow_up_questions}

请为这些问题提供更详细的信息。"""

    EXTRACTION_PROMPT = """基于以上对话，请提取以下信息为结构化格式：

1. 权限矩阵（如有）：按顺序列出每个批准角色、批准标准、并行/顺序方式
2. 聚合条件（如有）：描述需要观察的趋势、窗口大小、判断规则
3. 临时措施（如有）：描述有效期、失效条件、升级规则
4. 隔离范围（如有）：描述隔离维度、规则、影响的产品数量

请以 JSON 格式返回。"""

    @staticmethod
    def generate_first_round(expert_name: str, workflow_name: str,
                             dimension: QuestionCategory,
                             questions: List[LLMQuestion]) -> str:
        """生成第一轮提示词"""
        questions_text = "\n".join([f"{q.to_prompt()}" for q in questions])
        return Phase3APromptTemplate.FIRST_ROUND_PROMPT.format(
            expert_name=expert_name,
            workflow_name=workflow_name,
            dimension=dimension.value,
            questions=questions_text
        )


class Phase3ACollectionPipeline:
    """Phase 3-A 数据采集流程"""

    def __init__(self):
        self.question_set = Phase3AQuestionSet()

    def create_collection_plan(self, expert_name: str, workflow_name: str) -> Dict[str, Any]:
        """
        为指定的专家和工作流创建采集计划

        Args:
            expert_name: 专家名字
            workflow_name: 工作流名称

        Returns:
            采集计划，包含问题分组和执行步骤
        """
        return {
            'expert_name': expert_name,
            'workflow_name': workflow_name,
            'phases': [
                {
                    'phase': 1,
                    'dimension': QuestionCategory.PERMISSION_HIERARCHY,
                    'questions': self.question_set.get_questions_by_category(
                        QuestionCategory.PERMISSION_HIERARCHY
                    ),
                    'estimated_time_minutes': 15
                },
                {
                    'phase': 2,
                    'dimension': QuestionCategory.AGGREGATION_CONDITIONS,
                    'questions': self.question_set.get_questions_by_category(
                        QuestionCategory.AGGREGATION_CONDITIONS
                    ),
                    'estimated_time_minutes': 15
                },
                {
                    'phase': 3,
                    'dimension': QuestionCategory.TEMPORARY_MEASURES,
                    'questions': self.question_set.get_questions_by_category(
                        QuestionCategory.TEMPORARY_MEASURES
                    ),
                    'estimated_time_minutes': 15
                },
                {
                    'phase': 4,
                    'dimension': QuestionCategory.TRACEABILITY,
                    'questions': self.question_set.get_questions_by_category(
                        QuestionCategory.TRACEABILITY
                    ),
                    'estimated_time_minutes': 15
                },
                {
                    'phase': 5,
                    'dimension': QuestionCategory.EXCEPTION_HANDLING,
                    'questions': self.question_set.get_questions_by_category(
                        QuestionCategory.EXCEPTION_HANDLING
                    ),
                    'estimated_time_minutes': 10
                }
            ],
            'total_estimated_time_minutes': 70,
            'success_criteria': [
                '至少 50% 的问题有明确答案',
                '权限矩阵有 2+ 个不同角色',
                '隔离范围清晰定义',
                '临时措施的有效期明确'
            ]
        }

    def quality_checklist(self) -> List[str]:
        """采集质量检查清单"""
        return [
            '✓ 所有权限角色名称一致（使用标准术语）',
            '✓ 批准标准具体可测量（避免模糊语言如"大约"、"可能"）',
            '✓ 聚合条件的窗口大小和操作符明确',
            '✓ 临时措施的有效期有具体数值（时间或产品数量）',
            '✓ 隔离规则涵盖主要的根本原因情景',
            '✓ 升级规则清晰定义',
            '✓ 已确认是否存在跨工作流的规则',
            '✓ 已获取具体的真实案例示例',
            '✓ 所有关键术语已解释',
            '✓ 已验证信息的一致性和完整性'
        ]
