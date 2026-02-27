export function getScoreColor(score: number): string {
  const s = Math.min(100, score);
  if (s <= 25) return '#22c55e';
  if (s <= 50) return '#eab308';
  if (s <= 75) return '#f97316';
  return '#ef4444';
}

export function getScoreTextClass(score: number): string {
  const s = Math.min(100, score);
  if (s <= 25) return 'text-green-600 dark:text-green-400';
  if (s <= 50) return 'text-yellow-600 dark:text-yellow-400';
  if (s <= 75) return 'text-orange-600 dark:text-orange-400';
  return 'text-red-600 dark:text-red-400';
}

const sizes = {
  sm: { outer: 'w-10 h-10', inset: 'inset-1', text: 'text-[10px]' },
  md: { outer: 'w-14 h-14', inset: 'inset-1', text: 'text-xs' },
  lg: { outer: 'w-20 h-20', inset: 'inset-1.5', text: 'text-base' },
} as const;

type CircularScoreProps = {
  score: number;
  size?: keyof typeof sizes;
};

export function CircularScore({ score, size = 'md' }: CircularScoreProps) {
  const s = Math.min(100, score);
  const color = getScoreColor(s);
  const textClass = getScoreTextClass(s);
  const deg = (s / 100) * 360;
  const { outer, inset, text } = sizes[size];

  return (
    <div
      className={`relative ${outer} rounded-full shrink-0`}
      style={{
        background: `conic-gradient(${color} ${deg}deg, #e5e7eb ${deg}deg 360deg)`,
      }}
    >
      <div
        className={`absolute ${inset} rounded-full bg-white dark:bg-gray-800 flex items-center justify-center`}
      >
        <span className={`font-bold ${text} ${textClass}`}>
          {s.toFixed(0)}
        </span>
      </div>
    </div>
  );
}
