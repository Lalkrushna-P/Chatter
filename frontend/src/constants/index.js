export const RISK_META = {
  emergency: {
    label: "Emergency",
    color: "bg-red-600",
    text: "text-red-700",
    ring: "ring-red-200",
    bg: "bg-red-50",
    description: "Potential medical emergency — seek immediate care.",
  },
  urgent: {
    label: "Urgent",
    color: "bg-orange-500",
    text: "text-orange-700",
    ring: "ring-orange-200",
    bg: "bg-orange-50",
    description: "Seek prompt medical evaluation.",
  },
  routine: {
    label: "Routine consultation",
    color: "bg-amber-400",
    text: "text-amber-700",
    ring: "ring-amber-200",
    bg: "bg-amber-50",
    description: "Consider scheduling a healthcare appointment.",
  },
  self_care: {
    label: "Self-care / monitor",
    color: "bg-emerald-500",
    text: "text-emerald-700",
    ring: "ring-emerald-200",
    bg: "bg-emerald-50",
    description: "Monitor symptoms; seek care if they worsen.",
  },
  unknown: {
    label: "Assessing",
    color: "bg-slate-400",
    text: "text-slate-600",
    ring: "ring-slate-200",
    bg: "bg-slate-50",
    description: "Gathering more information.",
  },
};

export const GREETING =
  "Tell me what symptoms you're experiencing. I'll ask a few questions to help assess how urgent your situation may be.";

export const LAB_FLAG_META = {
  high: { label: "High", className: "bg-red-100 text-red-700" },
  low: { label: "Low", className: "bg-orange-100 text-orange-700" },
  normal: { label: "Normal", className: "bg-emerald-100 text-emerald-700" },
};

export const DISCLAIMER =
  "This is a health screening and guidance tool, not a diagnosis and not a substitute for a qualified healthcare professional. If you think this is an emergency, contact your local emergency services now.";
