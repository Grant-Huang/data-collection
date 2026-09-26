#!/usr/bin/env python3
"""
异常场景测试：用DAG生成系统测试各种真实场景

测试DAG生成系统在面对以下问题时的鲁棒性：
- 思维跳跃
- 言语断续
- 自我纠正
- 信息重复
- 碎片化信息
- 流程中断
- 复杂条件
- 主观评价混合
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from expert_interview_edge_cases import ExpertInterviewEdgeCases, EdgeCaseScenario


@dataclass
class TestResult:
    """测试结果"""
    scenario_id: str
    scenario_name: str
    category: str
    status: str  # PASS / FAIL / PARTIAL / ERROR
    nodes_extracted: int
    edges_extracted: int
    expected_nodes_min: int
    expected_nodes_max: int
    challenges_handled: List[str]
    challenges_failed: List[str]
    error_message: str = None
    notes: str = None


class EdgeCaseTestRunner:
    """异常场景测试运行器"""

    def __init__(self):
        self.edge_cases = ExpertInterviewEdgeCases()
        self.results: List[TestResult] = []

    def extract_flow_from_conversation(self, conversation: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        从对话中提取流程信息
        这是一个简化的实现，真实系统会更复杂
        """
        nodes = []
        edges = []
        actors = set()
        decisions = []

        node_counter = 0

        # 关键词映射
        keywords_activity = [
            '检查', '诊断', '分析', '检测', '隔离', '验证', '测试',
            '调整', '修复', '更换', '清理', '重启', '重置', '查看', '看'
        ]

        keywords_decision = [
            '如果', '如果是', '是否', '能否', '可能', '判断', '决定',
            '或者', '或', '要么'
        ]

        keywords_parallel = [
            '并行', '同时', '一起', '两个团队', '分别'
        ]

        keywords_retry = [
            '重试', '重复', '再次', '再来', '循环', '反复'
        ]

        # 第一步：创建节点
        for turn in conversation:
            text = turn.get("text", "").lower()
            speaker = turn.get("speaker", "")

            if speaker != "采集系统":  # 只处理专家的陈述
                actors.add(speaker)

                # 检测活动
                for keyword in keywords_activity:
                    if keyword in text:
                        node_id = f"node_{node_counter}"
                        nodes.append({
                            "node_id": node_id,
                            "type": "activity",
                            "label": f"活动_{node_counter}",
                            "description": text[:50],
                            "turn": turn.get("turn", 0)
                        })
                        node_counter += 1
                        break  # 每个回合最多一个节点

                # 检测决策
                for keyword in keywords_decision:
                    if keyword in text:
                        node_id = f"decision_{len(decisions)}"
                        decisions.append({
                            "node_id": node_id,
                            "type": "decision",
                            "label": f"判断_{len(decisions)}",
                            "description": text[:50],
                            "turn": turn.get("turn", 0)
                        })
                        break

        # 合并决策节点
        nodes.extend(decisions)

        # 第二步：简单的边连接（按时间顺序）
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
            "statistics": {
                "total_turns": len(conversation),
                "expert_turns": len([t for t in conversation if t.get("speaker") != "采集系统"]),
                "activities": len([n for n in nodes if n["type"] == "activity"]),
                "decisions": len([n for n in nodes if n["type"] == "decision"])
            }
        }

    def test_scenario(self, scenario: EdgeCaseScenario) -> TestResult:
        """
        测试单个场景
        """
        print(f"\n🧪 测试: {scenario.scenario_id} - {scenario.scenario_name}")
        print(f"   类别: {scenario.category}")

        try:
            # 提取流程
            flow = self.extract_flow_from_conversation(scenario.conversation)
            nodes = flow["nodes"]
            edges = flow["edges"]

            # 评估结果
            num_nodes = len(nodes)
            num_edges = len(edges)

            # 判断是否通过
            challenges_handled = []
            challenges_failed = []

            # 基本启发式评估
            if num_nodes >= 3:  # 至少应该有3个节点
                challenges_handled.append("节点提取")
            else:
                challenges_failed.append("节点提取不足")

            if num_edges >= 2:  # 至少应该有2条边
                challenges_handled.append("边连接")
            else:
                challenges_failed.append("边连接不足")

            # 检查是否识别了关键挑战
            if scenario.category == "思维不连贯":
                if any("处理" in str(n) for n in nodes):
                    challenges_handled.append("逻辑重组")

            if scenario.category == "条件分支":
                if any("判断" in str(n) for n in nodes):
                    challenges_handled.append("决策识别")

            # 确定状态
            if len(challenges_failed) == 0:
                status = "PASS"
            elif len(challenges_handled) > len(challenges_failed):
                status = "PARTIAL"
            else:
                status = "FAIL"

            result = TestResult(
                scenario_id=scenario.scenario_id,
                scenario_name=scenario.scenario_name,
                category=scenario.category,
                status=status,
                nodes_extracted=num_nodes,
                edges_extracted=num_edges,
                expected_nodes_min=5,
                expected_nodes_max=15,
                challenges_handled=challenges_handled,
                challenges_failed=challenges_failed
            )

            # 输出结果
            print(f"   状态: {status}")
            print(f"   提取节点: {num_nodes}, 边: {num_edges}")
            print(f"   ✅ 处理: {', '.join(challenges_handled) if challenges_handled else '无'}")
            if challenges_failed:
                print(f"   ❌ 失败: {', '.join(challenges_failed)}")

            return result

        except Exception as e:
            print(f"   ❌ 错误: {str(e)}")
            return TestResult(
                scenario_id=scenario.scenario_id,
                scenario_name=scenario.scenario_name,
                category=scenario.category,
                status="ERROR",
                nodes_extracted=0,
                edges_extracted=0,
                expected_nodes_min=5,
                expected_nodes_max=15,
                challenges_handled=[],
                challenges_failed=["系统异常"],
                error_message=str(e)
            )

    def run_all_tests(self) -> List[TestResult]:
        """运行所有异常场景测试"""
        print("\n" + "="*80)
        print("🧪 异常场景综合测试")
        print("="*80)

        scenarios = self.edge_cases.list_all_scenarios()

        for scenario in scenarios:
            result = self.test_scenario(scenario)
            self.results.append(result)

        return self.results

    def generate_test_report(self, output_file: str = "edge_case_test_report.json"):
        """生成测试报告"""
        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
                "total_tests": len(self.results),
                "passed": len([r for r in self.results if r.status == "PASS"]),
                "partial": len([r for r in self.results if r.status == "PARTIAL"]),
                "failed": len([r for r in self.results if r.status == "FAIL"]),
                "errors": len([r for r in self.results if r.status == "ERROR"])
            },
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "scenario_name": r.scenario_name,
                    "category": r.category,
                    "status": r.status,
                    "nodes_extracted": r.nodes_extracted,
                    "edges_extracted": r.edges_extracted,
                    "expected_nodes_min": r.expected_nodes_min,
                    "expected_nodes_max": r.expected_nodes_max,
                    "challenges_handled": r.challenges_handled,
                    "challenges_failed": r.challenges_failed,
                    "error_message": r.error_message,
                    "notes": r.notes
                }
                for r in self.results
            ]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 测试报告已保存到: {output_file}")

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

        print("\n" + "="*80)
        print("📊 测试总结")
        print("="*80)
        print(f"\n总测试数:     {total}")
        print(f"✅ 通过:      {passed} ({passed*100//total if total>0 else 0}%)")
        print(f"⚠️  部分:      {partial}")
        print(f"❌ 失败:      {failed}")
        print(f"🔥 错误:      {errors}")

        print("\n" + "-"*80)
        print("按类别分类:")
        print("-"*80)

        by_category = {}
        for result in self.results:
            cat = result.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(result)

        for category, results in sorted(by_category.items()):
            passed_cat = len([r for r in results if r.status == "PASS"])
            total_cat = len(results)
            print(f"  {category:15} {passed_cat}/{total_cat} 通过")

        print("\n" + "-"*80)
        print("节点提取统计:")
        print("-"*80)
        avg_nodes = sum(r.nodes_extracted for r in self.results) / len(self.results)
        avg_edges = sum(r.edges_extracted for r in self.results) / len(self.results)
        print(f"  平均节点数: {avg_nodes:.1f}")
        print(f"  平均边数:   {avg_edges:.1f}")


def main():
    """主测试函数"""
    runner = EdgeCaseTestRunner()

    # 运行所有测试
    runner.run_all_tests()

    # 打印总结
    runner.print_summary()

    # 生成报告
    runner.generate_test_report()

    # 导出异常场景
    runner.edge_cases.export_to_json("expert_interview_edge_cases.json")


if __name__ == "__main__":
    main()
