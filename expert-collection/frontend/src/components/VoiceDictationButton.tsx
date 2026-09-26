// Desktop mic button for the chat input (IMPLEMENTATION_PLAN.md section 17.5). While
// recording, a strip above the input shows what's being recognized; "完成" puts the text
// into the input box for the expert to check and edit before sending (the transcript is
// never sent automatically -- recognition errors on equipment/process names are common).
import { useVoiceDictation } from "../hooks/useVoiceDictation";

export function VoiceDictationButton({ disabled, onText }: { disabled?: boolean; onText: (text: string) => void }) {
  const { state, liveText, error, start, stop } = useVoiceDictation();
  const active = state === "connecting" || state === "recording" || state === "finishing";

  return (
    <>
      {(active || error) && (
        <div
          style={{
            position: "absolute", left: 16, right: 16, bottom: "100%", marginBottom: 6,
            background: error && !active ? "#fef2f2" : "#eef4fc", border: `1px solid ${error && !active ? "#fecaca" : "#bfd4f2"}`,
            borderRadius: 8, padding: "8px 10px", fontSize: 12.5, display: "flex", alignItems: "center", gap: 8,
          }}
        >
          <div style={{ flex: 1, minWidth: 0, color: error && !active ? "#991b1b" : "#1f2937", maxHeight: 96, overflowY: "auto" }}>
            {active
              ? liveText || (state === "connecting" ? "正在连接语音识别……" : state === "finishing" ? "正在整理最后一句……" : "正在听，您可以一次把整个过程讲完……")
              : error}
          </div>
          {active ? (
            <>
              <button onClick={() => stop("cancel")} style={stripBtn(false)}>取消</button>
              <button
                disabled={state === "finishing"}
                onClick={async () => {
                  const text = await stop("keep");
                  if (text) onText(text);
                }}
                style={stripBtn(true)}
              >
                完成
              </button>
            </>
          ) : null}
        </div>
      )}
      <button
        aria-label="语音输入"
        title="语音输入：说完点「完成」，文字会放进输入框，可以修改后再发送"
        disabled={disabled || active}
        onClick={start}
        style={{
          border: "1px solid #d0d5dd", borderRadius: 8, width: 40, flexShrink: 0,
          background: active ? "#eef4fc" : "#fff", cursor: disabled || active ? "default" : "pointer", fontSize: 16,
        }}
      >
        🎤
      </button>
    </>
  );
}

function stripBtn(primary: boolean) {
  return {
    border: primary ? "none" : "1px solid #d0d5dd", borderRadius: 6, padding: "4px 12px", fontSize: 12,
    background: primary ? "#2a78d6" : "#fff", color: primary ? "#fff" : "#475569", cursor: "pointer", flexShrink: 0,
  } as const;
}
