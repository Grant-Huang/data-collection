// PRD 4.4.2 item 4: pending items must each carry a "回到会话说明" -- the mobile DAG page has
// no edit entry (2.2), so every structural gap the validator finds needs a plain-language
// prompt telling the expert what to say back in the conversation, not the raw error code.
import type { ValidationIssue } from "../api/types";

const HINTS: Record<string, string> = {
  missing_start: "回到会话里从头讲一遍这件事是怎么开始的。",
  missing_end: "回到会话里告诉我：这个流程正常结束的标志是什么？",
  decision_needs_two_branches: "回到会话里告诉我：除了已经说的那种情况，还有没有别的处理方式？",
  parallel_split_needs_two: "回到会话里告诉我：一起做的另一件事具体是什么？",
  parallel_join_needs_two: "回到会话里确认一下，两边完成后是怎么汇合的。",
  merge_needs_two: "回到会话里告诉我，还有哪条路径也会汇入这一步。",
  isolated_node: "回到会话里说明这一步和前后是怎么连起来的。",
  empty_condition: "回到会话里说清楚这条分支具体的判断条件是什么。",
  cycle_detected: "回到会话里换个说法描述返工，不用说“回到第几步重做”，直接说“如果不合格会怎样”。",
  duplicate_node_id: "这是系统内部问题，无需专家处理，请联系管理员。",
  duplicate_edge_id: "这是系统内部问题，无需专家处理，请联系管理员。",
  dangling_edge: "这是系统内部问题，无需专家处理，请联系管理员。",
  start_has_incoming: "这是系统内部问题，无需专家处理，请联系管理员。",
  end_has_outgoing: "这是系统内部问题，无需专家处理，请联系管理员。",
};

export function hintForIssue(issue: ValidationIssue): string {
  return HINTS[issue.code] ?? `回到会话里补充说明：${issue.message}`;
}
