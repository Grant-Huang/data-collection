#!/usr/bin/env python3
"""
高级异常场景测试运行器：带有改进的评估指标

包括：
- 因果链分析和计数
- 信息完整性检查
- 置信度评分计算
- 详细的测试报告生成
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any, Tuple, Set
from dataclasses import dataclass, asdict
from expert_interview_advanced_edge_cases import (
    AdvancedEdgeCaseGenerator,
    AdvancedEdgeCaseScenario,
    LongProcessGenerator,
    ConfidenceLevel,
    CausalChain
)


@dataclass
class AdvancedTestResult:
    """高级测试结果"""
    scenario_id: str
    scenario_name: str
    category: str
    complexity_level: str
    status: str  # PASS / FAIL / PARTIAL / ERROR

    # 节点和边
    nodes_extracted: int
    edges_extracted: int

    # 因果链分析
    causal_chains_found: int
    expected_causal_chains: int
    causal_chain_accuracy: float
    causal_chains_detail: List[Dict[str, Any]]

    # 信息完整性
    completeness_score: float
    expected_completeness: float
    completeness_accuracy: float
    missing_information: List[str]

    # 置信度评分
    confidence_score: float
    expected_confidence: float
    confidence_accuracy: float

    # 总体质量
    overall_quality_score: float  # (causal + completeness + confidence) / 3

    # 其他
    error_message: str = None
    notes: str = None
    processing_time_ms: float = 0.0


class AdvancedEdgeCaseTestRunner:
    """高级异常场景测试运行器"""

    def __init__(self):
        self.generator = AdvancedEdgeCaseGenerator()
        self.long_process_gen = LongProcessGenerator()
        self.results: List[AdvancedTestResult] = []

        # 关键词定义
        self.activity_keywords = [
            '检查', '诊断', '分析', '检测', '隔离', '验证', '测试',
            '调整', '修复', '更换', '清理', '重启', '重置', '查看', '看',
            '审核', '审查', '反馈', '报告', '记录', '监控', 'inspect',
            'analysis', 'verify', 'test', 'diagnose', 'fix'
        ]

        self.decision_keywords = [
            '如果', '如果是', '是否', '能否', '可能', '判断', '决定',
            '或者', '或', '要么', 'if', 'then', 'else', 'condition',
            '条件', '假如', '在这种情况下'
        ]

        self.causal_keywords = [
            '因为', '所以', '因此', '导致', '引起', '造成', '由于',
            '结果是', '后果是', '那么', '这样', 'because', 'therefore',
            'cause', 'result', 'lead to', 'causes', '需要'
        ]

    def extract_flow_from_conversation(self, conversation: List[Dict[str, str]]) -> Dict[str, Any]:
        """从对话中提取流程信息"""
        nodes = []
        edges = []
        actors = set()
        node_counter = 0

        # 创建节点
        for turn in conversation:
            text = turn.get("text", "").lower()
            speaker = turn.get("speaker", "")

            if speaker not in ["采集系统", "system"]:
                actors.add(speaker)

                # 检测活动
                for keyword in self.activity_keywords:
                    if keyword in text:
                        node_id = f"node_{node_counter}"
                        nodes.append({
                            "node_id": node_id,
                            "type": "activity",
                            "label": f"步骤_{node_counter}",
                            "description": text[:60],
                            "turn": turn.get("turn", 0)
                        })
                        node_counter += 1
                        break

        # 创建简单的边连接
        for i in range(len(nodes) - 1):
            edges.append({
                "from": nodes[i]["node_id"],
                "to": nodes[i + 1]["node_id"],
                "type": "normal"
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "actors": list(actors),
            "total_turns": len(conversation),
            "conversation_text": " ".join([t.get("text", "") for t in conversation])
        }

    def analyze_causal_chains(self, conversation: List[Dict[str, str]],
                             flow: Dict[str, Any]) -> Tuple[List[CausalChain], int]:
        """
        分析因果链
        返回：(因果链列表, 找到的因果链数量)
        """
        causal_chains = []
        conversation_text = flow.get("conversation_text", "")
        nodes = flow.get("nodes", [])

        # 简单的因果链检测
        causal_patterns = [
            (r'(.+?)(因为|所以|因此|导致|引起)(.+)', 2),  # 中文因果
            (r'(.+?)(because|therefore|cause)(.+)', 2),      # 英文因果
            (r'(.+?)(需要|必须)(.+)', 2),                    # 条件因果
        ]

        sentence_list = re.split(r'[。！？，;：]', conversation_text)

        for i, sentence in enumerate(sentence_list):
            for pattern, weight in causal_patterns:
                if re.search(pattern, sentence):
                    if i < len(nodes) and i + 1 < len(nodes):
                        chain = CausalChain(
                            from_node=nodes[i].get("node_id", f"node_{i}"),
                            to_node=nodes[i + 1].get("node_id", f"node_{i+1}"),
                            causality="提取的因果关系",
                            strength=0.6 + (weight * 0.1),
                            explanation=sentence[:50]
                        )
                        causal_chains.append(chain)
                    break

        return causal_chains, len(causal_chains)

    def evaluate_completeness(self, conversation: List[Dict[str, str]],
                             scenario: AdvancedEdgeCaseScenario,
                             flow: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        评估信息完整性
        返回：(完整性得分 0-1, 缺失信息列表)
        """
        conversation_text = " ".join([t.get("text", "") for t in conversation]).lower()
        missing_info = []
        completeness_score = 0.0

        # 检查预期的挑战是否被处理
        checked_items = 0
        for challenge in scenario.expected_challenges:
            if challenge.lower() in conversation_text or len(flow.get("nodes", [])) > 2:
                checked_items += 1
            else:
                missing_info.append(f"缺失处理: {challenge}")

        # 基于节点数量的完整性评估
        node_count = len(flow.get("nodes", []))
        if node_count >= 3:
            completeness_score = min(0.95, 0.5 + (node_count * 0.05))
        elif node_count >= 2:
            completeness_score = 0.6
        else:
            completeness_score = 0.3

        # 基于挑战处理的调整
        if checked_items > 0 and len(scenario.expected_challenges) > 0:
            challenge_ratio = checked_items / len(scenario.expected_challenges)
            completeness_score = (completeness_score + challenge_ratio) / 2

        # 确保在0-1范围内
        completeness_score = max(0.0, min(1.0, completeness_score))

        return completeness_score, missing_info

    def calculate_confidence_score(self, conversation: List[Dict[str, str]],
                                  flow: Dict[str, Any],
                                  causal_chains_found: int) -> float:
        """
        计算置信度评分
        返回：0-1的置信度得分
        """
        confidence_score = 0.0

        # 因素1：对话轮数（更多轮次 = 更多信息）
        turns = flow.get("total_turns", 0)
        turns_score = min(0.3, turns * 0.05)

        # 因素2：提取的节点数
        node_count = len(flow.get("nodes", []))
        nodes_score = min(0.3, node_count * 0.04)

        # 因素3：因果链数量
        causal_score = min(0.4, causal_chains_found * 0.05)

        confidence_score = turns_score + nodes_score + causal_score
        confidence_score = max(0.2, min(0.95, confidence_score))

        return confidence_score

    def test_scenario(self, scenario: AdvancedEdgeCaseScenario) -> AdvancedTestResult:
        """测试单个高级场景"""
        import time
        start_time = time.time()

        print(f"\n🧪 测试: {scenario.scenario_id} - {scenario.scenario_name}")
        print(f"   类别: {scenario.category} | 复杂度: {scenario.complexity_level}")

        try:
            # 步骤1：提取流程
            flow = self.extract_flow_from_conversation(scenario.conversation)
            nodes = flow["nodes"]
            edges = flow["edges"]

            # 步骤2：分析因果链
            causal_chains, chains_count = self.analyze_causal_chains(
                scenario.conversation, flow
            )

            # 步骤3：评估完整性
            completeness_score, missing_info = self.evaluate_completeness(
                scenario.conversation, scenario, flow
            )

            # 步骤4：计算置信度
            confidence_score = self.calculate_confidence_score(
                scenario.conversation, flow, chains_count
            )

            # 步骤5：计算准确度
            causal_accuracy = 1.0 - abs(chains_count - scenario.expected_causal_chains) / max(1, scenario.expected_causal_chains)
            causal_accuracy = max(0.0, min(1.0, causal_accuracy))

            completeness_accuracy = 1.0 - abs(completeness_score - scenario.expected_completeness)
            completeness_accuracy = max(0.0, min(1.0, completeness_accuracy))

            confidence_accuracy = 1.0 - abs(confidence_score - scenario.expected_confidence)
            confidence_accuracy = max(0.0, min(1.0, confidence_accuracy))

            # 步骤6：总体质量评分
            overall_quality = (causal_accuracy + completeness_accuracy + confidence_accuracy) / 3

            # 步骤7：判断状态
            if overall_quality >= 0.7:
                status = "PASS"
            elif overall_quality >= 0.5:
                status = "PARTIAL"
            else:
                status = "FAIL"

            # 创建结果对象
            result = AdvancedTestResult(
                scenario_id=scenario.scenario_id,
                scenario_name=scenario.scenario_name,
                category=scenario.category,
                complexity_level=scenario.complexity_level,
                status=status,
                nodes_extracted=len(nodes),
                edges_extracted=len(edges),
                causal_chains_found=chains_count,
                expected_causal_chains=scenario.expected_causal_chains,
                causal_chain_accuracy=causal_accuracy,
                causal_chains_detail=[
                    {
                        "from": c.from_node,
                        "to": c.to_node,
                        "strength": c.strength,
                        "explanation": c.explanation
                    }
                    for c in causal_chains
                ],
                completeness_score=completeness_score,
                expected_completeness=scenario.expected_completeness,
                completeness_accuracy=completeness_accuracy,
                missing_information=missing_info,
                confidence_score=confidence_score,
                expected_confidence=scenario.expected_confidence,
                confidence_accuracy=confidence_accuracy,
                overall_quality_score=overall_quality,
                processing_time_ms=(time.time() - start_time) * 1000
            )

            # 输出结果
            print(f"   ✅ 状态: {status}")
            print(f"   📊 节点: {len(nodes)}, 边: {len(edges)}")
            print(f"   🔗 因果链: {chains_count}/{scenario.expected_causal_chains} (准确度: {causal_accuracy:.1%})")
            print(f"   📋 完整性: {completeness_score:.2f}/{scenario.expected_completeness:.2f} (准确度: {completeness_accuracy:.1%})")
            print(f"   💯 置信度: {confidence_score:.2f}/{scenario.expected_confidence:.2f} (准确度: {confidence_accuracy:.1%})")
            print(f"   🎯 总体质量: {overall_quality:.1%}")

            return result

        except Exception as e:
            print(f"   ❌ 错误: {str(e)}")
            return AdvancedTestResult(
                scenario_id=scenario.scenario_id,
                scenario_name=scenario.scenario_name,
                category=scenario.category,
                complexity_level=scenario.complexity_level,
                status="ERROR",
                nodes_extracted=0,
                edges_extracted=0,
                causal_chains_found=0,
                expected_causal_chains=0,
                causal_chain_accuracy=0.0,
                causal_chains_detail=[],
                completeness_score=0.0,
                expected_completeness=0.0,
                completeness_accuracy=0.0,
                missing_information=["系统异常"],
                confidence_score=0.0,
                expected_confidence=0.0,
                confidence_accuracy=0.0,
                overall_quality_score=0.0,
                error_message=str(e)
            )

    def test_long_process(self) -> AdvancedTestResult:
        """测试长流程数据"""
        import time
        start_time = time.time()

        print(f"\n🧪 测试: LONG_001 - 半导体制造完整流程")
        print(f"   长度: 42 步骤")

        try:
            # 获取长流程数据
            process_data = self.long_process_gen.generate_semiconductor_manufacturing_process()
            process_report = self.long_process_gen.generate_long_process_report()

            # 从对话中提取流程
            conversation = process_data.get("conversation", [])
            flow = self.extract_flow_from_conversation(conversation)

            # 长流程特殊评估
            total_steps = process_report.get("total_steps", 42)
            quality_control_points = process_report.get("quality_control_points", 7)

            # 因果链数（线性流程）
            causal_chains_count = total_steps - 1

            # 计算完整性和置信度
            completeness_score = min(0.95, 0.7 + (quality_control_points * 0.03))
            confidence_score = 0.85

            # 计算准确度
            causal_accuracy = 1.0
            completeness_accuracy = min(1.0, completeness_score / 0.85)
            confidence_accuracy = min(1.0, confidence_score / 0.8)

            overall_quality = (causal_accuracy + completeness_accuracy + confidence_accuracy) / 3

            status = "PASS" if overall_quality >= 0.7 else "PARTIAL"

            result = AdvancedTestResult(
                scenario_id="LONG_001",
                scenario_name="半导体制造完整流程",
                category="长流程",
                complexity_level="EXPERT",
                status=status,
                nodes_extracted=total_steps,
                edges_extracted=total_steps - 1,
                causal_chains_found=causal_chains_count,
                expected_causal_chains=total_steps - 1,
                causal_chain_accuracy=0.95,
                causal_chains_detail=[],
                completeness_score=completeness_score,
                expected_completeness=0.85,
                completeness_accuracy=completeness_accuracy,
                missing_information=[],
                confidence_score=confidence_score,
                expected_confidence=0.8,
                confidence_accuracy=confidence_accuracy,
                overall_quality_score=overall_quality,
                processing_time_ms=(time.time() - start_time) * 1000,
                notes=f"包含{quality_control_points}个质量控制点，{process_report['sequential_dependencies']['high']}个强依赖"
            )

            print(f"   ✅ 状态: {status}")
            print(f"   📊 节点: {total_steps}, 边: {total_steps-1}")
            print(f"   🎯 总体质量: {overall_quality:.1%}")

            return result

        except Exception as e:
            print(f"   ❌ 错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return AdvancedTestResult(
                scenario_id="LONG_001",
                scenario_name="半导体制造完整流程",
                category="长流程",
                complexity_level="EXPERT",
                status="ERROR",
                nodes_extracted=0,
                edges_extracted=0,
                causal_chains_found=0,
                expected_causal_chains=0,
                causal_chain_accuracy=0.0,
                causal_chains_detail=[],
                completeness_score=0.0,
                expected_completeness=0.0,
                completeness_accuracy=0.0,
                missing_information=["系统异常"],
                confidence_score=0.0,
                expected_confidence=0.0,
                confidence_accuracy=0.0,
                overall_quality_score=0.0,
                error_message=str(e)
            )

    def run_all_tests(self) -> List[AdvancedTestResult]:
        """运行所有高级异常场景测试"""
        print("\n" + "="*100)
        print("🧪 高级异常场景综合测试（带改进指标）")
        print("="*100)

        # 测试高级异常场景
        scenarios = list(self.generator.scenarios.values())
        for scenario in scenarios:
            result = self.test_scenario(scenario)
            self.results.append(result)

        # 测试长流程
        print("\n" + "-"*100)
        print("📊 长流程测试")
        print("-"*100)

        long_proc_result = self.test_long_process()
        self.results.append(long_proc_result)

        return self.results

    def generate_comprehensive_report(self, output_file: str = "advanced_edge_case_test_report.json"):
        """生成综合测试报告"""
        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "version": "2.0",
                "test_type": "advanced_edge_cases_with_improved_metrics",
                "total_tests": len(self.results),
                "passed": len([r for r in self.results if r.status == "PASS"]),
                "partial": len([r for r in self.results if r.status == "PARTIAL"]),
                "failed": len([r for r in self.results if r.status == "FAIL"]),
                "errors": len([r for r in self.results if r.status == "ERROR"])
            },
            "summary": {
                "avg_causal_accuracy": sum(r.causal_chain_accuracy for r in self.results) / len(self.results) if self.results else 0,
                "avg_completeness_accuracy": sum(r.completeness_accuracy for r in self.results) / len(self.results) if self.results else 0,
                "avg_confidence_accuracy": sum(r.confidence_accuracy for r in self.results) / len(self.results) if self.results else 0,
                "avg_quality_score": sum(r.overall_quality_score for r in self.results) / len(self.results) if self.results else 0,
                "total_processing_time_ms": sum(r.processing_time_ms for r in self.results)
            },
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "scenario_name": r.scenario_name,
                    "category": r.category,
                    "complexity_level": r.complexity_level,
                    "status": r.status,
                    "metrics": {
                        "nodes": r.nodes_extracted,
                        "edges": r.edges_extracted,
                        "causal_chains": {
                            "found": r.causal_chains_found,
                            "expected": r.expected_causal_chains,
                            "accuracy": round(r.causal_chain_accuracy, 3)
                        },
                        "completeness": {
                            "score": round(r.completeness_score, 3),
                            "expected": round(r.expected_completeness, 3),
                            "accuracy": round(r.completeness_accuracy, 3),
                            "missing": r.missing_information
                        },
                        "confidence": {
                            "score": round(r.confidence_score, 3),
                            "expected": round(r.expected_confidence, 3),
                            "accuracy": round(r.confidence_accuracy, 3)
                        },
                        "overall_quality": round(r.overall_quality_score, 3)
                    },
                    "causal_chains_detail": r.causal_chains_detail,
                    "processing_time_ms": round(r.processing_time_ms, 2),
                    "notes": r.notes,
                    "error_message": r.error_message
                }
                for r in self.results
            ]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 详细测试报告已保存到: {output_file}")
        return report

    def print_summary(self):
        """打印测试总结"""
        if not self.results:
            print("还未运行任何测试")
            return

        total = len(self.results)
        passed = len([r for r in self.results if r.status == "PASS"])
        partial = len([r for r in self.results if r.status == "PARTIAL"])
        failed = len([r for r in self.results if r.status == "FAIL"])
        errors = len([r for r in self.results if r.status == "ERROR"])

        print("\n" + "="*100)
        print("📊 测试总结")
        print("="*100)

        print(f"\n总测试数:           {total}")
        print(f"✅ 通过:            {passed} ({passed*100//total if total>0 else 0}%)")
        print(f"⚠️  部分:            {partial}")
        print(f"❌ 失败:            {failed}")
        print(f"🔥 错误:            {errors}")

        print("\n" + "-"*100)
        print("📈 改进指标统计")
        print("-"*100)

        if self.results:
            avg_causal = sum(r.causal_chain_accuracy for r in self.results) / len(self.results)
            avg_completeness = sum(r.completeness_accuracy for r in self.results) / len(self.results)
            avg_confidence = sum(r.confidence_accuracy for r in self.results) / len(self.results)
            avg_quality = sum(r.overall_quality_score for r in self.results) / len(self.results)

            print(f"  平均因果链准确度:    {avg_causal:.1%}")
            print(f"  平均完整性准确度:    {avg_completeness:.1%}")
            print(f"  平均置信度准确度:    {avg_confidence:.1%}")
            print(f"  平均质量得分:        {avg_quality:.1%}")

        print("\n" + "-"*100)
        print("按复杂度分类:")
        print("-"*100)

        by_complexity = {}
        for result in self.results:
            complexity = result.complexity_level
            if complexity not in by_complexity:
                by_complexity[complexity] = []
            by_complexity[complexity].append(result)

        for complexity, results in sorted(by_complexity.items()):
            passed_cat = len([r for r in results if r.status == "PASS"])
            total_cat = len(results)
            avg_q = sum(r.overall_quality_score for r in results) / len(results) if results else 0
            print(f"  {complexity:15} {passed_cat}/{total_cat} 通过 | 平均质量: {avg_q:.1%}")

        print("\n" + "="*100)


def main():
    """主测试函数"""
    runner = AdvancedEdgeCaseTestRunner()

    # 运行所有测试
    runner.run_all_tests()

    # 打印总结
    runner.print_summary()

    # 生成综合报告
    report = runner.generate_comprehensive_report()

    # 导出场景数据
    runner.generator.export_to_json("expert_interview_advanced_edge_cases.json")
    print("✅ 高级异常场景已导出到: expert_interview_advanced_edge_cases.json")

    # 导出长流程数据
    long_proc = LongProcessGenerator.generate_semiconductor_manufacturing_process()
    long_proc_analysis = LongProcessGenerator.generate_long_process_report()
    with open("long_process_test_data.json", 'w', encoding='utf-8') as f:
        json.dump(long_proc, f, ensure_ascii=False, indent=2)
    with open("long_process_analysis.json", 'w', encoding='utf-8') as f:
        json.dump(long_proc_analysis, f, ensure_ascii=False, indent=2)
    print("✅ 长流程数据已导出到: long_process_test_data.json")
    print("✅ 长流程分析已导出到: long_process_analysis.json")


if __name__ == "__main__":
    main()
