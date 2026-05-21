import { useMemo } from "react";

interface Props {
  series: { label: string; color: string; values: number[] }[];
  timeAxis: number[];
  height?: number;
}

// Swiss palette: ink + oxblood + a few neutrals
const COLORS = [
  "#0a0a0a",
  "#8a0f1c",
  "#444444",
  "#7a7a7a",
  "#2a2a2a",
  "#a0a0a0",
  "#5a0a14",
  "#c0392b",
];

export function QueueChart({ series, timeAxis, height = 300 }: Props) {
  const { width, padding, maxY, points } = useMemo(() => {
    const width = 800;
    const padding = { l: 48, r: 16, t: 12, b: 32 };
    const allValues = series.flatMap((s) => s.values);
    const maxY = Math.max(1, ...allValues);
    const xs = timeAxis;
    const maxX = xs[xs.length - 1] ?? 1;

    const px = (x: number) =>
      padding.l + ((x - 0) / (maxX || 1)) * (width - padding.l - padding.r);
    const py = (y: number) =>
      height - padding.b - (y / maxY) * (height - padding.t - padding.b);

    const points = series.map((s) => ({
      label: s.label,
      color: s.color,
      d:
        s.values.length === 0
          ? ""
          : s.values
              .map((v, i) => `${i === 0 ? "M" : "L"}${px(xs[i] ?? i)},${py(v)}`)
              .join(" "),
    }));

    return { width, padding, maxY, points };
  }, [series, timeAxis, height]);

  const ticks = 5;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => (maxY * i) / ticks);
  const xMax = timeAxis[timeAxis.length - 1] ?? 0;
  const xTicks = Array.from({ length: 6 }, (_, i) => (xMax * i) / 5);

  return (
    <div>
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        style={{ height }}
      >
        {/* axes — swiss-style hairlines */}
        <line
          x1={padding.l}
          x2={padding.l}
          y1={padding.t}
          y2={height - padding.b}
          stroke="#0a0a0a"
          strokeWidth={1}
        />
        <line
          x1={padding.l}
          x2={width - padding.r}
          y1={height - padding.b}
          y2={height - padding.b}
          stroke="#0a0a0a"
          strokeWidth={1}
        />
        {/* y grid */}
        {yTicks.map((t, i) => {
          const y =
            height - padding.b - (t / maxY) * (height - padding.t - padding.b);
          return (
            <g key={`y${i}`}>
              <line
                x1={padding.l}
                x2={width - padding.r}
                y1={y}
                y2={y}
                stroke="#e6e6e6"
                strokeWidth={0.5}
              />
              <text
                x={padding.l - 8}
                y={y + 4}
                fill="#0a0a0a"
                fontSize="10"
                fontFamily="JetBrains Mono, monospace"
                textAnchor="end"
              >
                {t.toFixed(0)}
              </text>
            </g>
          );
        })}
        {/* x ticks */}
        {xTicks.map((t, i) => {
          const x =
            padding.l + (t / (xMax || 1)) * (width - padding.l - padding.r);
          return (
            <text
              key={`x${i}`}
              x={x}
              y={height - 12}
              fill="#0a0a0a"
              fontSize="10"
              fontFamily="JetBrains Mono, monospace"
              textAnchor="middle"
            >
              {t.toFixed(0)}s
            </text>
          );
        })}
        {points.map((p) => (
          <path
            key={p.label}
            d={p.d}
            stroke={p.color}
            strokeWidth="1.5"
            fill="none"
          />
        ))}
      </svg>
      <div className="row" style={{ marginTop: 12, fontSize: 11 }}>
        {series.map((s) => (
          <span
            key={s.label}
            style={{
              color: "#0a0a0a",
              textTransform: "uppercase",
              letterSpacing: "0.12em",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 14,
                height: 2,
                background: s.color,
              }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function colorFor(i: number): string {
  return COLORS[i % COLORS.length];
}
