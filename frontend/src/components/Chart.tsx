/**
 * 查询结果图表组件
 * 根据结果结构和后端推荐的图表规格，渲染 KPI 大数字、柱状图、折线图或环形图。
 * 单序列只用一个品牌色（moss），不画多余图例；数值靠悬停 tooltip 与坐标轴承载。
 */
import { BarChart3 } from "lucide-react";
import { columnKeys, normalizeRows, toNumber } from "../lib/data";
import { formatNumber } from "../lib/format";
import type { ChartSpec } from "../types/agent";

// 与全局设计系统一致的图表颜色：主序列用 moss，文本/网格用 ink 的不同透明度
const SERIES = "#2f6b4f";
const INK = "#20201d";
const MUTED = "rgba(32, 32, 29, 0.5)";
const GRID = "rgba(32, 32, 29, 0.1)";
const AXIS = "rgba(32, 32, 29, 0.18)";

type KpiItem = { label: string; value: number };
type SeriesChart = {
  kind: "bar" | "line" | "pie";
  labels: string[];
  values: number[];
  xLabel: string;
  yLabel: string;
  title?: string;
};
type Resolved = { kind: "kpi"; items: KpiItem[]; title?: string } | SeriesChart;

function isNumericColumn(rows: Array<Record<string, unknown>>, column: string) {
  const numeric = rows.filter((row) => toNumber(row[column]) !== null).length;
  return numeric > 0 && numeric >= rows.length * 0.5;
}

function isTimeColumn(name: string, labels: string[]) {
  if (/时间|日期|日|月|年|季|周|date|month|year|quarter|week|day/i.test(name)) {
    return true;
  }
  return labels.some(
    (label) =>
      /^\d{4}[-/]\d{1,2}/.test(label) ||
      /^\d{4}年/.test(label) ||
      /^\d{4}\s*Q[1-4]/i.test(label),
  );
}

function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function resolveChart(
  rows: Array<Record<string, unknown>>,
  columns: string[],
  spec?: ChartSpec | null,
): Resolved | null {
  // 1. 优先使用后端推荐的图表规格
  if (spec && spec.type !== "table") {
    if (spec.type === "kpi") {
      const numericColumns = columns.filter((column) => isNumericColumn(rows, column));
      if (numericColumns.length === 0) return null;
      return {
        kind: "kpi",
        items: numericColumns.map((column) => ({
          label: column,
          value: toNumber(rows[0][column]) ?? 0,
        })),
        title: spec.title,
      };
    }

    const x = spec.x_axis && columns.includes(spec.x_axis) ? spec.x_axis : null;
    const y = spec.y_axis && columns.includes(spec.y_axis) ? spec.y_axis : null;
    if (x && y) {
      const pairs = rows
        .map((row) => ({ label: String(row[x] ?? ""), value: toNumber(row[y]) }))
        .filter((pair): pair is { label: string; value: number } => pair.value !== null);
      if (pairs.length > 0) {
        const kind = spec.type === "line" ? "line" : spec.type === "pie" ? "pie" : "bar";
        return {
          kind,
          labels: pairs.map((pair) => pair.label),
          values: pairs.map((pair) => pair.value),
          xLabel: x,
          yLabel: y,
          title: spec.title,
        };
      }
    }
  }

  // 2. 无规格时按结果结构自动识别
  if (rows.length === 1) {
    const numericColumns = columns.filter((column) => isNumericColumn(rows, column));
    if (numericColumns.length === 0) return null;
    return {
      kind: "kpi",
      items: numericColumns.map((column) => ({
        label: column,
        value: toNumber(rows[0][column]) ?? 0,
      })),
    };
  }

  const x = columns.find((column) => !isNumericColumn(rows, column)) ?? columns[0];
  const y = columns.find((column) => column !== x && isNumericColumn(rows, column));
  if (!x || !y) return null;

  const pairs = rows
    .map((row) => ({ label: String(row[x] ?? ""), value: toNumber(row[y]) }))
    .filter((pair): pair is { label: string; value: number } => pair.value !== null);
  if (pairs.length < 1 || pairs.length > 30) return null;

  return {
    kind: isTimeColumn(x, pairs.map((pair) => pair.label)) ? "line" : "bar",
    labels: pairs.map((pair) => pair.label),
    values: pairs.map((pair) => pair.value),
    xLabel: x,
    yLabel: y,
  };
}

function niceStep(raw: number) {
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const residual = raw / magnitude;
  if (residual < 1.5) return magnitude;
  if (residual < 3) return 2 * magnitude;
  if (residual < 7) return 5 * magnitude;
  return 10 * magnitude;
}

function niceTicks(max: number) {
  if (max <= 0) return [0];
  const step = niceStep(max / 4);
  const ticks: number[] = [];
  for (let value = 0; value <= max + step * 0.0001; value += step) {
    ticks.push(value);
  }
  return ticks;
}

function KpiTiles({ chart }: { chart: Extract<Resolved, { kind: "kpi" }> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {chart.items.map((item) => (
        <div key={item.label} className="border border-ink/10 bg-white/70 px-4 py-3">
          <div className="text-xs text-ink/55">{item.label}</div>
          <div className="mt-1 text-3xl font-semibold tabular-nums text-ink">
            {formatNumber(item.value)}
          </div>
        </div>
      ))}
    </div>
  );
}

function BarChart({ chart }: { chart: SeriesChart }) {
  const width = 640;
  const height = 320;
  const margin = { top: 20, right: 12, bottom: 44, left: 60 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const max = Math.max(...chart.values, 0);
  const ticks = niceTicks(max);
  const baselineY = margin.top + innerHeight;
  const yScale = (value: number) => margin.top + innerHeight - (value / (max || 1)) * innerHeight;
  const slot = innerWidth / chart.labels.length;
  const barWidth = Math.min(22, slot * 0.6);
  const showValues = chart.labels.length <= 6;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      role="img"
      aria-label={chart.title ?? `${chart.xLabel} 与 ${chart.yLabel}`}
    >
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={margin.left} y1={yScale(tick)} x2={width - margin.right} y2={yScale(tick)} stroke={GRID} strokeWidth={1} />
          <text x={margin.left - 8} y={yScale(tick)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill={MUTED}>
            {formatNumber(tick)}
          </text>
        </g>
      ))}
      <line x1={margin.left} y1={baselineY} x2={width - margin.right} y2={baselineY} stroke={AXIS} strokeWidth={1} />

      {chart.labels.map((label, index) => {
        const value = chart.values[index];
        const x = margin.left + slot * index + (slot - barWidth) / 2;
        const y = yScale(value);
        const heightValue = baselineY - y;
        const radius = Math.min(4, barWidth / 2, heightValue);
        const path =
          `M ${x} ${baselineY} ` +
          `L ${x} ${y + radius} ` +
          `Q ${x} ${y} ${x + radius} ${y} ` +
          `L ${x + barWidth - radius} ${y} ` +
          `Q ${x + barWidth} ${y} ${x + barWidth} ${y + radius} ` +
          `L ${x + barWidth} ${baselineY} Z`;

        return (
          <g key={`${label}-${index}`}>
            <path d={path} fill={SERIES}>
              <title>{`${label}：${formatNumber(value)}`}</title>
            </path>
            {showValues && (
              <text x={x + barWidth / 2} y={y - 6} textAnchor="middle" fontSize={11} fill={INK}>
                {formatNumber(value)}
              </text>
            )}
            <text
              x={margin.left + slot * index + slot / 2}
              y={baselineY + 16}
              textAnchor="middle"
              fontSize={11}
              fill={MUTED}
            >
              {truncate(label, 8)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function LineChart({ chart }: { chart: SeriesChart }) {
  const width = 640;
  const height = 320;
  const margin = { top: 20, right: 16, bottom: 44, left: 60 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const max = Math.max(...chart.values, 0);
  const ticks = niceTicks(max);
  const baselineY = margin.top + innerHeight;
  const yScale = (value: number) => margin.top + innerHeight - (value / (max || 1)) * innerHeight;

  const count = chart.labels.length;
  const xScale = (index: number) =>
    count === 1 ? margin.left + innerWidth / 2 : margin.left + (index / (count - 1)) * innerWidth;
  const points = chart.values.map((value, index) => ({ x: xScale(index), y: yScale(value) }));
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${baselineY} L ${points[0].x} ${baselineY} Z`;
  const labelEvery = Math.max(1, Math.ceil(count / 8));
  const last = points[points.length - 1];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      role="img"
      aria-label={chart.title ?? `${chart.xLabel} 与 ${chart.yLabel}`}
    >
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={margin.left} y1={yScale(tick)} x2={width - margin.right} y2={yScale(tick)} stroke={GRID} strokeWidth={1} />
          <text x={margin.left - 8} y={yScale(tick)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill={MUTED}>
            {formatNumber(tick)}
          </text>
        </g>
      ))}
      <line x1={margin.left} y1={baselineY} x2={width - margin.right} y2={baselineY} stroke={AXIS} strokeWidth={1} />

      <path d={areaPath} fill={SERIES} opacity={0.1} />
      <path d={linePath} fill="none" stroke={SERIES} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

      {points.map((point, index) => (
        <circle key={index} cx={point.x} cy={point.y} r={6} fill="transparent">
          <title>{`${chart.labels[index]}：${formatNumber(chart.values[index])}`}</title>
        </circle>
      ))}
      {last && (
        <circle cx={last.x} cy={last.y} r={4} fill={SERIES} stroke="#fffaf1" strokeWidth={2} />
      )}

      {chart.labels.map((label, index) =>
        index % labelEvery === 0 ? (
          <text
            key={`${label}-${index}`}
            x={xScale(index)}
            y={baselineY + 16}
            textAnchor="middle"
            fontSize={11}
            fill={MUTED}
          >
            {truncate(label, 8)}
          </text>
        ) : null,
      )}
    </svg>
  );
}

function DonutChart({ chart }: { chart: SeriesChart }) {
  const size = 220;
  const center = size / 2;
  const outerRadius = 84;
  const innerRadius = 56;
  const total = chart.values.reduce((sum, value) => sum + value, 0);
  if (total <= 0) return null;

  const gap = 0.02;
  let cursor = -Math.PI / 2;
  const slices = chart.values.map((value, index) => {
    const fraction = value / total;
    const start = cursor;
    const end = cursor + fraction * Math.PI * 2;
    cursor = end;
    return { label: chart.labels[index], value, fraction, start, end };
  });

  const slicePath = (start: number, end: number) => {
    const s = start + gap / 2;
    const e = end - gap / 2;
    const large = e - s > Math.PI ? 1 : 0;
    const x0 = center + outerRadius * Math.cos(s);
    const y0 = center + outerRadius * Math.sin(s);
    const x1 = center + outerRadius * Math.cos(e);
    const y1 = center + outerRadius * Math.sin(e);
    const x2 = center + innerRadius * Math.cos(e);
    const y2 = center + innerRadius * Math.sin(e);
    const x3 = center + innerRadius * Math.cos(s);
    const y3 = center + innerRadius * Math.sin(s);
    return (
      `M ${x0} ${y0} ` +
      `A ${outerRadius} ${outerRadius} 0 ${large} 1 ${x1} ${y1} ` +
      `L ${x2} ${y2} ` +
      `A ${innerRadius} ${innerRadius} 0 ${large} 0 ${x3} ${y3} Z`
    );
  };

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:gap-6">
      <svg viewBox={`0 0 ${size} ${size}`} className="h-48 w-48 shrink-0" role="img" aria-label={chart.title ?? `${chart.xLabel} 构成`}>
        {slices.map((slice, index) => (
          <path
            key={`${slice.label}-${index}`}
            d={slicePath(slice.start, slice.end)}
            fill={SERIES}
            stroke="#fffaf1"
            strokeWidth={2}
          >
            <title>{`${slice.label}：${formatNumber(slice.value)}（${(slice.fraction * 100).toFixed(1)}%）`}</title>
          </path>
        ))}
      </svg>
      <ul className="min-w-0 space-y-1.5 text-sm">
        {slices.map((slice, index) => (
          <li key={`${slice.label}-${index}`} className="flex items-center gap-2">
            <span className="grid h-2.5 w-2.5 shrink-0 place-items-center rounded-full bg-moss" />
            <span className="truncate text-ink/75">{truncate(slice.label, 12)}</span>
            <span className="ml-auto tabular-nums text-ink/55">
              {formatNumber(slice.value)} · {(slice.fraction * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Chart({ data, spec }: { data: unknown; spec?: ChartSpec | null }) {
  const rows = normalizeRows(data);
  const columns = columnKeys(rows);
  const chart = resolveChart(rows, columns, spec);
  if (!chart) return null;

  return (
    <section className="mt-4 overflow-hidden border border-ink/10 bg-white/70 shadow-line">
      <div className="flex items-center gap-2 border-b border-ink/10 px-4 py-3">
        <BarChart3 className="h-4 w-4 text-moss" aria-hidden="true" />
        <span className="text-sm font-semibold text-ink">{chart.title ?? "数据图表"}</span>
      </div>
      <div className="px-4 py-4">
        {chart.kind === "kpi" && <KpiTiles chart={chart} />}
        {chart.kind === "bar" && <BarChart chart={chart} />}
        {chart.kind === "line" && <LineChart chart={chart} />}
        {chart.kind === "pie" && <DonutChart chart={chart} />}
      </div>
    </section>
  );
}
