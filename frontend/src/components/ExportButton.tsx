/**
 * 查询结果导出组件
 * 提供 CSV 和 JSON 两种导出方式
 */
import { Download, FileJson } from "lucide-react";
import { downloadFile, toCsv, toJson } from "../lib/export";

function makeFilename(ext: string) {
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  return `问数结果-${stamp}.${ext}`;
}

export function ExportButton({ data }: { data: unknown }) {
  const exportCsv = () => {
    downloadFile(makeFilename("csv"), toCsv(data), "text/csv;charset=utf-8");
  };

  const exportJson = () => {
    downloadFile(makeFilename("json"), toJson(data), "application/json;charset=utf-8");
  };

  return (
    <div className="mt-3 flex items-center gap-2">
      <button
        type="button"
        onClick={exportCsv}
        className="inline-flex h-9 items-center gap-1.5 border border-ink/15 bg-white/70 px-3 text-sm font-medium text-ink transition hover:border-moss/40 hover:bg-white"
      >
        <Download className="h-4 w-4 text-moss" aria-hidden="true" />
        导出 CSV
      </button>
      <button
        type="button"
        onClick={exportJson}
        className="inline-flex h-9 items-center gap-1.5 border border-ink/15 bg-white/70 px-3 text-sm font-medium text-ink transition hover:border-moss/40 hover:bg-white"
      >
        <FileJson className="h-4 w-4 text-brass" aria-hidden="true" />
        导出 JSON
      </button>
    </div>
  );
}
