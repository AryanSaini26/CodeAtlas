import type { SVGProps } from "react";

const PATHS: Record<string, string[]> = {
  dashboard: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h7v7h-7z"],
  graph: [
    "M12 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
    "M3 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
    "M21 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
    "M12 7v4m0 2v2M5.5 17.5l5-4.5M13.5 13l5 4.5",
  ],
  search: ["M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"],
  analysis: ["M18 20V10", "M12 20V4", "M6 20v-6"],
  diff: [
    "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z",
    "M14 2v6h6",
    "M9 15h2m2 0h2",
    "M12 12v6",
  ],
  settings: [
    "M12 2a10 10 0 0 1 0 20A10 10 0 0 1 12 2z",
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  ],
  mcp: [
    "M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18",
  ],
  x: ["M18 6 6 18M6 6l12 12"],
  check: ["M20 6 9 17l-5-5"],
  chevronL: ["M15 18l-6-6 6-6"],
  chevronR: ["M9 18l6-6-6-6"],
  externalLink: [
    "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
    "M15 3h6v6",
    "M10 14 21 3",
  ],
  refresh: [
    "M23 4v6h-6",
    "M1 20v-6h6",
    "M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
  ],
  info: [
    "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z",
    "M12 16v-4",
    "M12 8h.01",
  ],
};

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 15,
  strokeWidth = 1.75,
  className = "",
  ...rest
}: {
  name: string;
  size?: number;
  strokeWidth?: number;
} & SVGProps<SVGSVGElement>) {
  const paths = PATHS[name] ?? PATHS.info;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...rest}
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}
