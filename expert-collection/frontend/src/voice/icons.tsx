// Three voice icons, one per input mode (see VoiceDictationButton.tsx / mobile/VoiceCapsuleInput.tsx
// and RealtimeVoiceDialog.tsx for where each is used):
//
// ① OrganizeIntoInputIcon -- "专家原话经过大模型整理以后进入输入框": mic + a sparkle (stands in
//    for the LLM cleanup pass) + a curved arrow feeding down into an input-box outline.
// ② RecognizeAndSendIcon -- "专家说完话以后不经过输入框，直接识别并发送到会话里": mic + a
//    straight arrow feeding directly into a chat bubble, skipping the input-box shape entirely
//    (the visual contrast with ① is the point -- no box in the middle).
// ③ RealtimeVoiceIcon -- the larger "实时语音会话" launcher, styled after ChatGPT's voice-mode
//    glyph: a ring around a cluster of soundwave bars, sized up from ①/② since it opens a
//    full overlay rather than acting on the input box.
//
// All three are plain stroked/filled SVG (currentColor) so they inherit whatever color the
// surrounding button sets, matching the rest of this app's inline-style icon buttons.
import type { CSSProperties } from "react";

interface IconProps {
  size?: number;
  style?: CSSProperties;
}

export function OrganizeIntoInputIcon({ size = 20, style }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={style} aria-hidden>
      {/* mic capsule */}
      <rect x="9.25" y="2.5" width="5.5" height="9" rx="2.75" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      {/* sparkle -- the LLM organizing pass */}
      <path
        d="M18.3 2.4l0.55 1.35 1.35 0.55-1.35 0.55-0.55 1.35-0.55-1.35-1.35-0.55 1.35-0.55z"
        fill="currentColor"
      />
      {/* curved feed-down arrow into the input box */}
      <path
        d="M12 14.5v3.1c0 .9-1.2 1.3-1.8.6l-.9-1.1"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* input-box outline at the bottom */}
      <rect x="2.5" y="18.7" width="19" height="3.3" rx="1.65" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

export function RecognizeAndSendIcon({ size = 20, style }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={style} aria-hidden>
      {/* mic capsule */}
      <rect x="2.5" y="2.5" width="5.5" height="9" rx="2.75" stroke="currentColor" strokeWidth="1.6" />
      <path d="M-0.25 11.5a5.5 5.5 0 0 0 11 0" transform="translate(0.25 0)" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      {/* straight arrow shooting past the input box, direct into the bubble */}
      <path d="M9.5 8h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="1.5 2.2" />
      <path d="M15.3 5.2l2.5 2.8-2.5 2.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      {/* chat bubble it lands in */}
      <path
        d="M13 13.2h7.2a1.3 1.3 0 0 1 1.3 1.3v4.4a1.3 1.3 0 0 1-1.3 1.3h-5l-2.4 2v-2h-1.1a1.3 1.3 0 0 1-1.3-1.3v-4.4a1.3 1.3 0 0 1 1.3-1.3z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface RealtimeIconProps extends IconProps {
  /** Bar heights animate via CSS when the caller adds a "listening"/"speaking" class. */
  active?: boolean;
}

export function RealtimeVoiceIcon({ size = 30, style, active }: RealtimeIconProps) {
  const bars = [7, 13, 18, 13, 7];
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={style} aria-hidden>
      <circle cx="16" cy="16" r="14.5" stroke="currentColor" strokeWidth="1.4" opacity={0.35} />
      {bars.map((h, i) => (
        <rect
          key={i}
          x={16 - 10 + i * 5}
          y={16 - h / 2}
          width="3"
          height={h}
          rx="1.5"
          fill="currentColor"
          style={
            active
              ? { transformOrigin: "center", animation: `voice-bar-pulse 0.9s ease-in-out ${i * 0.1}s infinite` }
              : undefined
          }
        />
      ))}
      <style>{`@keyframes voice-bar-pulse{0%,100%{transform:scaleY(0.5)}50%{transform:scaleY(1.15)}}`}</style>
    </svg>
  );
}
