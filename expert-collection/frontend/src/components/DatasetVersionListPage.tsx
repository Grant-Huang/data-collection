// Dashboard「查看全部」-- 分页 + 可查询的完整数据集版本列表，从 Dashboard 首屏（只看最新
// 版本）点「查看全部」进来，选中一行再回到首屏、把 Dashboard 切到查看那个版本。
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { DatasetVersionSummary, SourceType } from "../api/types";

const PAGE_SIZE = 10;

const BAND_COLOR: Record<string, string> = { good: "#0ca30c", warning: "#fab219", poor: "#ec835a", insufficient_sample: "#94a3b8" };

interface Props {
  sourceType: SourceType;
  onBack: () => void;
  onSelectVersion: (version: DatasetVersionSummary) => void;
}

export function DatasetVersionListPage({ sourceType, onBack, onSelectVersion }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [items, setItems] = useState<DatasetVersionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchDatasetVersions(sourceType, { query, page, pageSize: PAGE_SIZE, includeArchived });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [sourceType, query, page, includeArchived]);

  useEffect(() => {
    load();
  }, [load]);

  // 换来源 / 换查询词 / 切换是否含已归档时回到第 1 页，避免停在一个可能已经不存在的页码上。
  useEffect(() => {
    setPage(1);
  }, [sourceType, query, includeArchived]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            onClick={onBack}
            style={{ border: "1px solid #d0d5dd", background: "#fff", color: "#475569", borderRadius: 6, padding: "5px 10px", fontSize: 12, cursor: "pointer" }}
          >
            ← 返回
          </button>
          <div style={{ fontSize: 13, fontWeight: 700 }}>全部数据集版本（共 {total} 个）</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11.5, color: "#667085", cursor: "pointer" }}>
            <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
            含已归档
          </label>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="按版本名 / 版本号查询，如 v3"
            style={{ border: "1px solid #d0d5dd", borderRadius: 6, padding: "5px 10px", fontSize: 12, width: 220 }}
          />
        </div>
      </div>

      {loading ? (
        <div style={{ padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>加载中…</div>
      ) : items.length === 0 ? (
        <div style={{ padding: 32, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
          {query ? "没有匹配的版本。" : "还没有发布过版本。"}
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #e5e7eb", color: "#94a3b8", textAlign: "left" }}>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>版本</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>名称</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>工作流数</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>步骤总数</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>评分</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>发布时间</th>
              <th style={{ padding: "6px 8px", fontWeight: 600 }}>状态</th>
              <th style={{ padding: "6px 8px" }} />
            </tr>
          </thead>
          <tbody>
            {items.map((v) => (
              <tr key={v.id} style={{ borderBottom: "1px solid #f1f3f5" }}>
                <td style={{ padding: "8px" }}>v{v.version_number}</td>
                <td style={{ padding: "8px" }}>{v.name}</td>
                <td style={{ padding: "8px" }}>{v.workflow_count}</td>
                <td style={{ padding: "8px" }}>{v.total_steps}</td>
                <td style={{ padding: "8px" }}>
                  {v.readiness.overall !== null ? (
                    <span style={{ fontWeight: 700, color: BAND_COLOR[v.readiness.band] ?? "#475569" }}>{v.readiness.overall}</span>
                  ) : (
                    <span style={{ color: "#94a3b8" }}>样本不足</span>
                  )}
                </td>
                <td style={{ padding: "8px", color: "#667085" }}>{new Date(v.created_at).toLocaleDateString("zh-CN")}</td>
                <td style={{ padding: "8px" }}>
                  {v.archived && <span style={{ fontSize: 11, color: "#94a3b8" }}>已归档 </span>}
                  {v.is_gold && <span style={{ fontSize: 11, fontWeight: 700, color: "#b45309" }}>★ Gold</span>}
                </td>
                <td style={{ padding: "8px", textAlign: "right" }}>
                  <button
                    onClick={() => onSelectVersion(v)}
                    style={{ border: "1px solid #2a78d6", color: "#2a78d6", background: "#fff", borderRadius: 6, padding: "3px 10px", fontSize: 11.5, cursor: "pointer" }}
                  >
                    查看
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 16 }}>
        <button
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
          style={{ border: "1px solid #d0d5dd", background: "#fff", borderRadius: 6, padding: "4px 10px", fontSize: 12, cursor: page <= 1 ? "default" : "pointer", color: page <= 1 ? "#c0c5cd" : "#475569" }}
        >
          上一页
        </button>
        <span style={{ fontSize: 12, color: "#667085" }}>第 {page} / {totalPages} 页</span>
        <button
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages}
          style={{ border: "1px solid #d0d5dd", background: "#fff", borderRadius: 6, padding: "4px 10px", fontSize: 12, cursor: page >= totalPages ? "default" : "pointer", color: page >= totalPages ? "#c0c5cd" : "#475569" }}
        >
          下一页
        </button>
      </div>

      {error && (
        <div style={{ marginTop: 16, background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: 8, padding: "8px 12px", fontSize: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}
