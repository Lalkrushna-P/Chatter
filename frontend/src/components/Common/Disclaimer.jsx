import { DISCLAIMER } from "../../constants/index.js";

export default function Disclaimer() {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <span className="font-semibold">Important:</span> {DISCLAIMER}
    </div>
  );
}
