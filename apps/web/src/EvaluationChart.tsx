import type { AnalysisPoint } from "./types";

interface EvaluationChartProps {
  points: AnalysisPoint[];
  selectedPly: number;
  onSelect: (ply: number) => void;
}

export function EvaluationChart({ points, selectedPly, onSelect }: EvaluationChartProps) {
  const width = 520;
  const height = 150;
  const coordinates = points.map((point, index) => {
    const x = points.length <= 1 ? 0 : (index / (points.length - 1)) * width;
    const normalized = Math.max(-800, Math.min(800, point.score_cp));
    const y = height / 2 - (normalized / 800) * (height / 2 - 12);
    return { x, y, point };
  });
  const path = coordinates.map(({ x, y }) => `${x},${y}`).join(" ");

  return (
    <div className="evaluation-chart">
      <div className="chart-labels" aria-hidden="true">
        <span>White</span>
        <span>Equal</span>
        <span>Black</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Stockfish evaluation by ply">
        <defs>
          <linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f3d48c" stopOpacity="0.22" />
            <stop offset="0.5" stopColor="#63dab0" stopOpacity="0.05" />
            <stop offset="1" stopColor="#836be2" stopOpacity="0.2" />
          </linearGradient>
        </defs>
        <rect width={width} height={height} rx="12" fill="url(#chart-area)" />
        <line x1="0" x2={width} y1={height / 2} y2={height / 2} className="chart-zero" />
        {coordinates.length > 1 && <polyline points={path} className="chart-line" />}
        {coordinates.map(({ x, y, point }) => (
          <circle
            key={point.ply}
            cx={x}
            cy={y}
            r={point.ply === selectedPly ? 5.5 : 3.25}
            className={point.ply === selectedPly ? "chart-point selected" : "chart-point"}
          />
        ))}
      </svg>
      <div className="chart-scrubber" aria-label="Evaluation positions">
        {points.map((point) => (
          <button
            key={point.ply}
            className={point.ply === selectedPly ? "selected" : ""}
            onClick={() => onSelect(point.ply)}
            aria-label={`Show evaluation after ply ${point.ply}`}
          />
        ))}
      </div>
    </div>
  );
}
