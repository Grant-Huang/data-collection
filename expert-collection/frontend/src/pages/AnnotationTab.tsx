// 「数据录入与标注」页的「数据标注」tab -- 从 DashboardPage 挪过来（之前是嵌在 Dashboard 首屏
// 里的一块），入口是这里列出的记录清单（“从清单入口，非全”：一条条进，不是一个“全部标注”的
// 批量入口），点「去标注」打开 PriorAnnotationPanel。按来源（专家集/公有集）区分，跟 Dashboard
// 页保持一致的分类，但这里只关心当前最新版本要标注的记录，不关心已发布版本历史——历史版本列表
// 是 Dashboard「查看全部」的事。
//
// 权限：未来应该根据角色只显示专家能看到自己需要标注的那部分（PRD 16.2 的精神），这一轮先不
// 做，两个来源、全部记录对当前身份一样可见。
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Role, SourceType } from "../api/types";
import { DatasetRecordList } from "../components/DatasetRecordList";

export function AnnotationTab({ role }: { role: Role }) {
  const [sourceType, setSourceType] = useState<SourceType>("expert_collected");
  const [latestVersionId, setLatestVersionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (st: SourceType) => {
    setError(null);
    try {
      const versions = await api.listDatasetVersions(st);
      setLatestVersionId(versions[0]?.id ?? null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh(sourceType);
  }, [sourceType, refresh]);

  return (
    <div style={{ height: "100%", overflowY: "auto", background: "#f6f7f9" }}>
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "20px 24px 60px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}>
          <h1 style={{ fontSize: 18, fontWeight: 800, margin: 0 }}>数据标注</h1>
          <div style={{ display: "flex", border: "1px solid #d0d5dd", borderRadius: 999, overflow: "hidden", fontSize: 12.5 }}>
            {(["expert_collected", "public_extracted"] as SourceType[]).map((st) => (
              <button
                key={st}
                onClick={() => setSourceType(st)}
                style={{
                  border: "none", padding: "6px 14px", cursor: "pointer",
                  background: sourceType === st ? "#2a78d6" : "#fff",
                  color: sourceType === st ? "#fff" : "#475569", fontWeight: 600,
                }}
              >
                {st === "expert_collected" ? "专家集" : "公有集"}
              </button>
            ))}
          </div>
        </div>

        {!latestVersionId ? (
          <div style={{ background: "#fff", border: "1px dashed #d0d5dd", borderRadius: 10, padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            {sourceType === "expert_collected" ? "还没有发布过版本，先在「专家录入」完成并确认几条会话，发布后再回来标注。" : "还没有导入过公有集数据。"}
          </div>
        ) : (
          <DatasetRecordList
            versionId={latestVersionId}
            role={role}
            title={sourceType === "public_extracted" ? "Prior 标注（Public/LLM-derived Prior → Expert-annotated Prior）" : "专家复核（独立第二人确认 → Gold）"}
            emptyMessage="当前最新版本没有可标注的记录。"
          />
        )}

        {error && (
          <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
