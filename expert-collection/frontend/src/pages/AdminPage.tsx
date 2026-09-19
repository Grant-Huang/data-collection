// PRD 16, honestly scoped (IMPLEMENTATION_PLAN.md section 7): dataset publish/archive
// already live in Dashboard; this page surfaces the audit log those actions write to, plus
// a pointer to Settings. No user/role management -- there's no real account system yet.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditLogEntry } from "../api/types";

const ACTION_LABELS: Record<string, string> = {
  dataset_publish: "数据集发布", dataset_archive: "数据集归档", experiment_create: "创建实验",
};

export function AdminPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);

  useEffect(() => {
    api.getAuditLog().then(setEntries);
  }, []);

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "20px 24px 60px" }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>管理页面</h1>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16, fontSize: 12.5, color: "#667085" }}>
          数据集发布/归档在 Dashboard 页面操作；系统设置（LLM/语音/质量参数）在「系统设置」页面。
          用户与权限管理本轮未实现——当前没有真实账号体系，做一个假的账号列表页没有意义（IMPLEMENTATION_PLAN.md 第 7 节）。
        </div>

        <section style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 800, marginBottom: 4 }}>审计日志</div>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
            没有真实多用户登录，"谁"只能记到当前选择的身份，不是真实账号；只记录数据集发布/归档、实验创建这些真正在发生的操作。
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#667085" }}>
                <th style={{ padding: "8px 10px" }}>操作</th>
                <th style={{ padding: "8px 10px" }}>身份</th>
                <th style={{ padding: "8px 10px" }}>详情</th>
                <th style={{ padding: "8px 10px" }}>时间</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} style={{ borderTop: "1px solid #f1f3f5" }}>
                  <td style={{ padding: "8px 10px", fontWeight: 600, whiteSpace: "nowrap" }}>{ACTION_LABELS[e.action] ?? e.action}</td>
                  <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>{e.actor_role}</td>
                  <td style={{ padding: "8px 10px", color: "#667085" }}>{JSON.stringify(e.detail)}</td>
                  <td style={{ padding: "8px 10px", color: "#667085" }}>{new Date(e.created_at).toLocaleString("zh-CN")}</td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "#94a3b8" }}>还没有记录</td></tr>
              )}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
