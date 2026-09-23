// PRD 16, honestly scoped (IMPLEMENTATION_PLAN.md section 7): dataset publish/archive
// already live in Dashboard; this page surfaces the audit log those actions write to, plus
// a pointer to Settings. No user/role management -- there's no real account system yet.
//
// Import/export moved here from Dashboard: this page is only reachable when the current
// role is "admin" (DesktopApp's NAV gates the "管理页面" entry to minRole ["admin"]), so
// putting these actions here is this app's existing way of requiring admin permission --
// the same front-end role-gating pattern already used for the "归档当前版本" button.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditLogEntry, DatasetVersionSummary, SourceType } from "../api/types";
import { ImportPanel } from "../components/ImportPanel";

const ACTION_LABELS: Record<string, string> = {
  dataset_publish: "数据集发布", dataset_archive: "数据集归档", experiment_create: "创建实验",
  dataset_import: "数据集导入",
};

const EXPORT_FORMATS: { key: string; label: string }[] = [
  { key: "raw", label: "原始版" }, { key: "role_normalized", label: "角色归一化版" }, { key: "anonymized", label: "匿名版" },
];

export function AdminPage() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [sourceType, setSourceType] = useState<SourceType>("public_extracted");
  const [versions, setVersions] = useState<DatasetVersionSummary[]>([]);

  const refreshVersions = useCallback(async (st: SourceType) => {
    setVersions(await api.listDatasetVersions(st));
  }, []);

  useEffect(() => {
    api.getAuditLog().then(setEntries);
  }, []);

  useEffect(() => {
    refreshVersions(sourceType);
  }, [sourceType, refreshVersions]);

  const latest = versions[0] ?? null;

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "20px 24px 60px" }}>
        <h1 style={{ fontSize: 18, fontWeight: 800, marginTop: 0 }}>管理页面</h1>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16, fontSize: 12.5, color: "#667085" }}>
          数据集发布/归档在 Dashboard 页面操作；系统设置（LLM/语音/质量参数）在「系统设置」页面。
          用户与权限管理本轮未实现——当前没有真实账号体系，做一个假的账号列表页没有意义（IMPLEMENTATION_PLAN.md 第 7 节）。
        </div>

        <section style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 800 }}>数据集导入 / 导出</div>
            <div style={{ display: "flex", border: "1px solid #d0d5dd", borderRadius: 999, overflow: "hidden", fontSize: 12 }}>
              {(["expert_collected", "public_extracted"] as SourceType[]).map((st) => (
                <button
                  key={st}
                  onClick={() => setSourceType(st)}
                  style={{
                    border: "none", padding: "5px 12px", cursor: "pointer",
                    background: sourceType === st ? "#2a78d6" : "#fff",
                    color: sourceType === st ? "#fff" : "#475569", fontWeight: 600,
                  }}
                >
                  {st === "expert_collected" ? "专家集" : "公共集"}
                </button>
              ))}
            </div>
          </div>

          {sourceType === "public_extracted" && (
            <div style={{ marginBottom: 16 }}>
              <ImportPanel role="admin" onImported={() => refreshVersions(sourceType)} />
            </div>
          )}

          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>
            导出当前版本{latest ? `（v${latest.version_number}）` : ""}：
          </div>
          {latest ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {EXPORT_FORMATS.map((f) => (
                <a
                  key={f.key}
                  href={api.exportVersionUrl(latest.id, f.key)}
                  style={{ fontSize: 11.5, color: "#2a78d6", border: "1px solid #d0d5dd", borderRadius: 6, padding: "4px 10px", textDecoration: "none" }}
                >
                  {f.label}
                </a>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "#94a3b8" }}>该数据源尚未发布过版本，暂无可导出内容。</div>
          )}
        </section>

        <section style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 800, marginBottom: 4 }}>审计日志</div>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
            没有真实多用户登录，"谁"只能记到当前选择的身份，不是真实账号；只记录数据集发布/归档、导入、实验创建这些真正在发生的操作。
          </div>
          <table style={{ width: "100%", tableLayout: "fixed", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#667085" }}>
                <th style={{ padding: "8px 10px", width: 100 }}>操作</th>
                <th style={{ padding: "8px 10px", width: 70 }}>身份</th>
                <th style={{ padding: "8px 10px" }}>详情</th>
                <th style={{ padding: "8px 10px", width: 130 }}>时间</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} style={{ borderTop: "1px solid #f1f3f5" }}>
                  <td style={{ padding: "8px 10px", fontWeight: 600 }}>{ACTION_LABELS[e.action] ?? e.action}</td>
                  <td style={{ padding: "8px 10px" }}>{e.actor_role}</td>
                  <td style={{ padding: "8px 10px", color: "#667085", wordBreak: "break-all", whiteSpace: "normal" }}>
                    {JSON.stringify(e.detail)}
                  </td>
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
