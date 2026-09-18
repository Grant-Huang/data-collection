import { TipIcon } from "./TipIcon";

interface Props {
  label: string;
  value: string | number;
  tip: string;
  placeholder?: boolean;
}

export function MetricCard({ label, value, tip, placeholder }: Props) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "14px 16px", minWidth: 120 }}>
      <div style={{ fontSize: 11.5, color: "#667085", display: "flex", alignItems: "center" }}>
        {label}
        <TipIcon text={tip} />
      </div>
      <div style={{ fontSize: 22, fontWeight: 800, color: placeholder ? "#cbd5e1" : "#1f2937", marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}
