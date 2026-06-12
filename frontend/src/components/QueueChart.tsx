import { useMemo } from "react";

export interface BandSeries {
  label: string;
  color: string;
  median: number[];
  low: number[];
  high: number[];
}

interface Props {
  series: BandSeries[];
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
  const { width, padding, maxY, paths } = useMemo(() => {
    const width = 800;
    const padding = { l: 48, r: 16, t: 12, b: 32 };
    const allValues = series.flatMap((s) => [...s.high, ...s.median]);
    const maxY = Math.max(1, ...allValues);
    const xs = timeAxis;
    const maxX = xs[xs.length - 1] ?? 1;

    const px = (x: number) =>
      padding.l + ((x - 0) / (maxX || 1)) * (width - padding.l - padding.r);
    const py = (y: number) =>
      height - padding.b - (y / maxY) * (height - padding.t - padding.b);

    const line = (values: number[]) =>
      values.length === 0
        ? ""
        : values
            .map((v, i) => `${i === 0 ? "M" : "L"}${px(xs[i] ?? i)},${py(v)}`)
            .join(" ");

    // Banda p05–p95: contorno superior hacia adelante + inferior en reversa.
    const band = (low: number[], high: number[]) => {
      if (high.length === 0 || low.length !== high.length) return "";
      const fwd = high
        .map((v, i) => `${i === 0 ? "M" : "L"}${px(xs[i] ?? i)},${py(v)}`)
        .join(" ");
      const back = [...low]
        .map((v, i) => ({ v, i }))
        .reverse()
        .map(({ v, i }) => `L${px(xs[i] ?? i)},${py(v)}`)
        .join(" ");
      return `${fwd} ${back} Z`;
    };

    const paths = series.map((s) => ({
      label: s.label,
      color: s.color,
      median: line(s.median),
      band: band(s.low, s.high),
    }));

    return { width, padding, maxY, paths };
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
        {/* bandas p05–p95 debajo de las medianas */}
        {paths.map((p) =>
          p.band ? (
            <path
              key={`band-${p.label}`}
              d={p.band}
              fill={p.color}
              fillOpacity={0.13}
              stroke="none"
            />
          ) : null,
        )}
        {paths.map((p) => (
          <path
            key={p.label}
            d={p.median}
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
        <span style={{ color: "var(--muted, #777)", letterSpacing: "0.06em" }}>
          línea: mediana · banda: percentil 5–95 entre réplicas
        </span>
      </div>
    </div>
  );
}

export function colorFor(i: number): string {
  return COLORS[i % COLORS.length];
}
