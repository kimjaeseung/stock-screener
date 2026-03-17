import { useMemo } from 'react';
import { motion } from 'framer-motion';

interface Props {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export default function SparkLine({ data, width = 200, height = 50, color = '#00d26a' }: Props) {
  const { path, fillPath, totalLength } = useMemo(() => {
    if (!data || data.length < 2) return { path: '', fillPath: '', totalLength: 0 };
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const pad = 4;
    const w = width - pad * 2;
    const h = height - pad * 2;

    const points = data.map((v, i) => ({
      x: pad + (i / (data.length - 1)) * w,
      y: pad + (1 - (v - min) / range) * h,
    }));

    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const cp1x = (points[i - 1].x + points[i].x) / 2;
      d += ` C ${cp1x} ${points[i - 1].y}, ${cp1x} ${points[i].y}, ${points[i].x} ${points[i].y}`;
    }

    const last = points[points.length - 1];
    const first = points[0];
    const fillD = `${d} L ${last.x} ${height} L ${first.x} ${height} Z`;

    // Estimate path length
    const totalLength = points.reduce((acc, p, i) => {
      if (i === 0) return 0;
      const dx = p.x - points[i - 1].x;
      const dy = p.y - points[i - 1].y;
      return acc + Math.sqrt(dx * dx + dy * dy);
    }, 0);

    return { path: d, fillPath: fillD, totalLength };
  }, [data, width, height]);

  if (!path) return null;

  const isPositive = data[data.length - 1] >= data[0];
  const lineColor = isPositive ? color : '#ff3b30';
  const gradId = `spark-grad-${Math.random().toString(36).slice(2)}`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.3" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="1.5" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Fill area */}
      <motion.path
        d={fillPath}
        fill={`url(#${gradId})`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.3 }}
      />

      {/* Line */}
      <motion.path
        d={path}
        fill="none"
        stroke={lineColor}
        strokeWidth={1.5}
        strokeLinecap="round"
        filter="url(#glow)"
        style={{ strokeDasharray: totalLength + 10, strokeDashoffset: totalLength + 10 }}
        animate={{ strokeDashoffset: 0 }}
        transition={{ duration: 1.5, ease: 'easeInOut' }}
      />
    </svg>
  );
}
