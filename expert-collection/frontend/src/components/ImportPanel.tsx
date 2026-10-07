// PRD 12.2.1: upload JSON -> precheck (no write) -> precheck report -> confirm -> import.
// "Confirm" for public_extracted *is* the publish step (PRD 12.0 point 3) -- there's no
// separate draft pool for imported data the way expert collection has one.
import { useRef, useState, type CSSProperties, type ChangeEvent } from "react";
import { api, type ImportPrecheckReport } from "../api/client";
import type { Role } from "../api/types";

export function ImportPanel({ role, onImported }: { role: Role; onImported: () => void }) {
  const [rawText, setRawText] = useState("");
  const [report, setReport] = useState<ImportPrecheckReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setRawText(String(reader.result ?? ""));
    reader.readAsText(file);
  }

  async function handlePrecheck() {
    setError(null);
    setReport(null);
    let payload: unknown;
    try {
      payload = JSON.parse(rawText);
    } catch {
      setError("不是合法的 JSON，请检查格式");
      return;
    }
    setChecking(true);
    try {
      setReport(await api.importPrecheck(payload));
    } catch (e) {
      setError(String(e));
    } finally {
      setChecking(false);
    }
  }

  async function handleConfirm() {
    if (!report) return;
    setImporting(true);
    setError(null);
    try {
      const payload = JSON.parse(rawText);
      await api.importConfirm(payload, role, report.error_count === 0 ? false : true);
      setRawText("");
      setReport(null);
      onImported();
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20 }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>导入公有集</div>
      <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 12 }}>
        上传符合 <code>{"{dataset_meta, records[]}"}</code> 结构的 JSON 文件（对照 schema/workflow_graph_schema_v2.json），先预检、再确认导入——确认导入即发布，不进草稿池。
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input ref={fileRef} type="file" accept="application/json" onChange={handleFile} style={{ fontSize: 12 }} />
      </div>
      <textarea
        value={rawText}
        onChange={(e) => setRawText(e.target.value)}
        placeholder='粘贴 JSON，或用上方选择文件（格式：{"dataset_meta": {...}, "records": [...]}）'
        rows={6}
        style={{ width: "100%", fontSize: 11.5, fontFamily: "monospace", border: "1px solid #d0d5dd", borderRadius: 6, padding: 10, boxSizing: "border-box" }}
      />

      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button onClick={handlePrecheck} disabled={checking || !rawText.trim()} style={primaryBtn}>
          {checking ? "预检中…" : "预检"}
        </button>
        {report && (
          <button onClick={handleConfirm} disabled={importing || report.importable_records === 0} style={successBtn}>
            {importing ? "导入中…" : `确认导入（${report.importable_records}/${report.total_records} 条可导入）`}
          </button>
        )}
      </div>

      {error && <div style={{ marginTop: 10, color: "#991b1b", fontSize: 12 }}>{error}</div>}

      {report && (
        <div style={{ marginTop: 16, borderTop: "1px solid #f1f3f5", paddingTop: 16 }}>
          <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 12.5 }}>
            <Stat label="总记录数" value={report.total_records} />
            <Stat label="可导入" value={report.importable_records} />
            <Stat label="阻断错误" value={report.error_count} color={report.error_count > 0 ? "#d03b3b" : undefined} />
            <Stat label="警告" value={report.warning_count} color={report.warning_count > 0 ? "#fab219" : undefined} />
            <Stat label="用途建议" value={report.recommendation} isText />
          </div>
          {report.preview_readiness?.overall !== null && report.preview_readiness && (
            <div style={{ fontSize: 12.5, color: "#475569", marginBottom: 10 }}>
              预览 Dataset Readiness Score：<b>{report.preview_readiness.overall}</b>
            </div>
          )}
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 8 }}>{report.gold_annotation_note}</div>
          {report.issues.length > 0 && (
            <div style={{ maxHeight: 200, overflowY: "auto", fontSize: 11.5 }}>
              {report.issues.map((issue, i) => (
                <div key={i} style={{ padding: "4px 0", color: issue.level === "error" ? "#991b1b" : "#92400e" }}>
                  [{issue.level === "error" ? "错误" : "警告"}] {issue.record_id ? `${issue.record_id}：` : ""}{issue.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color, isText }: { label: string; value: string | number; color?: string; isText?: boolean }) {
  return (
    <div>
      <div style={{ color: "#94a3b8", fontSize: 11 }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: isText ? 12.5 : 15, color: color ?? "#1f2937" }}>{value}</div>
    </div>
  );
}

const primaryBtn: CSSProperties = { border: "none", background: "#2a78d6", color: "#fff", borderRadius: 6, padding: "7px 14px", fontSize: 12.5, cursor: "pointer" };
const successBtn: CSSProperties = { border: "none", background: "#0ca30c", color: "#fff", borderRadius: 6, padding: "7px 14px", fontSize: 12.5, cursor: "pointer" };
