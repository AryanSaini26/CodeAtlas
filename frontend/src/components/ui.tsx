import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  PropsWithChildren,
  ReactNode,
} from "react";

type ClassProps = { className?: string };

export const KIND_COLOR: Record<string, string> = {
  function: "#00f0ff",
  method: "#00dbe9",
  class: "#bd00ff",
  interface: "#a78bfa",
  module: "#71717a",
  variable: "#f59e0b",
  type: "#f87171",
};

export function kindColor(kind: string): string {
  return KIND_COLOR[kind] ?? "#71717a";
}

export function KindDot({ kind, size = 7 }: { kind: string; size?: number }) {
  return (
    <span
      className="inline-block rounded-full shrink-0"
      style={{
        width: size,
        height: size,
        backgroundColor: kindColor(kind),
      }}
    />
  );
}

export function KindBadge({ kind }: { kind: string }) {
  const color = kindColor(kind);
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-1.5 py-[1px] text-[11px] font-mono border"
      style={{
        backgroundColor: `${color}18`,
        borderColor: `${color}40`,
        color,
      }}
    >
      {kind}
    </span>
  );
}

export function Card({
  className = "",
  children,
  ...rest
}: PropsWithChildren<ClassProps & HTMLAttributes<HTMLDivElement>>) {
  return (
    <div className={`glass rounded-[10px] ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between border-b border-border px-4 pt-3.5 pb-3">
      <div>
        <h2 className="font-head font-bold text-[13px] text-text-1 leading-tight">
          {title}
        </h2>
        {subtitle ? (
          <p className="text-[11px] text-text-3 mt-0.5">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0 ml-2">{action}</div> : null}
    </div>
  );
}

export function CardBody({
  className = "",
  children,
}: PropsWithChildren<ClassProps>) {
  return <div className={`px-4 py-3.5 ${className}`}>{children}</div>;
}

export function StatTile({
  label,
  value,
  color = "#00f0ff",
}: {
  label: string;
  value: ReactNode;
  color?: string;
}) {
  return (
    <div className="glass rounded-[10px] px-5 py-4.5 relative overflow-hidden animate-fade-up">
      <div
        className="absolute -top-5 -right-5 w-20 h-20 rounded-full pointer-events-none"
        style={{
          backgroundColor: color,
          opacity: 0.06,
          filter: "blur(20px)",
        }}
      />
      <div className="text-[11px] uppercase tracking-[0.06em] text-text-3 mb-2">
        {label}
      </div>
      <div className="font-head font-bold text-[32px] text-text-1 leading-none">
        {value}
      </div>
    </div>
  );
}

export function Badge({
  children,
  tone = "default",
}: PropsWithChildren<{
  tone?: "default" | "success" | "warn" | "danger" | "cyan" | "violet";
}>) {
  const tones: Record<string, string> = {
    default: "bg-surface-hi text-text-2 border-border",
    success: "bg-good/10 text-good border-good/30",
    warn: "bg-amber/10 text-amber border-amber/30",
    danger: "bg-bad/10 text-bad border-bad/30",
    cyan: "bg-cyan/10 text-cyan border-cyan/25",
    violet: "bg-violet/10 text-violet border-violet/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-[7px] py-[2px] text-[11px] font-medium border ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return <input className={`input ${className}`} {...rest} />;
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...rest
}: PropsWithChildren<
  {
    variant?: "primary" | "ghost" | "danger";
    size?: "sm" | "md";
  } & ButtonHTMLAttributes<HTMLButtonElement>
>) {
  const variants = {
    primary: "btn-primary",
    ghost: "btn-ghost",
    danger: "btn-danger",
  } as const;
  const sizeCls =
    size === "sm" ? "!text-[11px] !px-2.5 !py-1" : "";
  return (
    <button
      className={`${variants[variant]} ${sizeCls} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
}: {
  icon?: ReactNode;
  title: string;
  hint?: ReactNode;
}) {
  return (
    <div className="text-center py-8 px-4 text-text-4">
      {icon ? <div className="mx-auto mb-2.5">{icon}</div> : null}
      <div className="text-[13px] text-text-3">{title}</div>
      {hint ? <div className="mt-1 text-[11px]">{hint}</div> : null}
    </div>
  );
}

export function Skeleton({
  className = "",
  w,
  h,
}: ClassProps & { w?: string | number; h?: string | number }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width: typeof w === "number" ? `${w}px` : w ?? "100%",
        height: typeof h === "number" ? `${h}px` : h ?? "14px",
      }}
    />
  );
}

export function ScoreBar({
  score,
  max = 1,
  color = "#00f0ff",
}: {
  score: number;
  max?: number;
  color?: string;
}) {
  const pct = Math.min((score / max) * 100, 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-surface-hi rounded overflow-hidden">
        <div
          className="h-full rounded transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono text-[11px] text-text-3 min-w-[52px] text-right">
        {score < 0.01 ? score.toFixed(5) : score.toFixed(2)}
      </span>
    </div>
  );
}

export function FilePath({
  path,
  line,
  className = "",
}: {
  path: string;
  line?: number | null;
  className?: string;
}) {
  return (
    <span className={`font-mono text-[11px] text-text-3 ${className}`}>
      {path}
      {line ? `:${line}` : ""}
    </span>
  );
}

export function PulseDot({ color = "#22c55e", size = 8 }: { color?: string; size?: number }) {
  return (
    <span
      className="inline-block rounded-full animate-pulse-dot"
      style={{ width: size, height: size, backgroundColor: color }}
    />
  );
}
