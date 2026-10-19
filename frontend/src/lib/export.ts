/**
 * 查询结果导出工具
 * 把前端已持有的结果数据导出为 CSV / JSON 并触发浏览器下载
 */
import { columnKeys, normalizeRows } from "./data";

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  // 含逗号、引号或换行时需要加引号包裹，并把内部引号转义
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function toCsv(data: unknown): string {
  const rows = normalizeRows(data);
  const columns = columnKeys(rows);
  const lines = [
    columns.map(csvCell).join(","),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
  ];
  // 前置 BOM，让 Excel 正确识别 UTF-8 中文
  return "﻿" + lines.join("\r\n");
}

export function toJson(data: unknown): string {
  return JSON.stringify(data, null, 2);
}

export function downloadFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
