import { PropsWithChildren, ReactNode, HTMLAttributes } from "react";

type ClassProps = { className?: string };

export function Card({
  className = "",
  children,
  ...rest
}: PropsWithChildren<ClassProps & HTMLAttributes<HTMLDivElement>>) {
  return (
    <div
      className={
        "rounded-lg border border-border bg-panel/60 backdrop-blur-sm " +
        className
      }
      {...rest}
    >
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
    <div className="flex items-start justify-between border-b border-border px-4 py-3">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {subtitle ? (
          <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardBody({
  className = "",
  children,
}: PropsWithChildren<ClassProps>) {
  return <div className={"p-4 " + className}>{children}</div>;
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-slate-100">{value}</div>
      {hint ? (
        <div className="mt-0.5 text-xs text-slate-500">{hint}</div>
      ) : null}
    </Card>
  );
}

export function Badge({
  children,
  tone = "default",
}: PropsWithChildren<{ tone?: "default" | "success" | "warn" | "danger" }>) {
  const colors: Record<string, string> = {
    default: "bg-slate-700 text-slate-200",
    success: "bg-emerald-900/50 text-emerald-300 border border-emerald-800",
    warn: "bg-amber-900/50 text-amber-300 border border-amber-800",
    danger: "bg-rose-900/50 text-rose-300 border border-rose-800",
  };
  return (
    <span
      className={
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium " +
        colors[tone]
      }
    >
      {children}
    </span>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return (
    <input
      className={
        "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm " +
        "text-slate-100 placeholder:text-slate-500 focus:outline-none " +
        "focus:ring-1 focus:ring-accent focus:border-accent " +
        className
      }
      {...rest}
    />
  );
}

export function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: PropsWithChildren<
  { variant?: "primary" | "ghost" } & React.ButtonHTMLAttributes<HTMLButtonElement>
>) {
  const base =
    "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50";
  const styles =
    variant === "primary"
      ? "bg-accent/20 text-accent border border-accent hover:bg-accent/30"
      : "text-slate-300 hover:text-slate-100 hover:bg-panel";
  return (
    <button className={base + " " + styles + " " + className} {...rest}>
      {children}
    </button>
  );
}

export function EmptyState({
  title,
  hint,
}: {
  title: string;
  hint?: ReactNode;
}) {
  return (
    <div className="text-center py-8 text-slate-500">
      <div className="text-sm">{title}</div>
      {hint ? <div className="mt-1 text-xs">{hint}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "" }: ClassProps) {
  return (
    <div
      className={
        "animate-pulse rounded-md bg-slate-800/60 " + className
      }
    />
  );
}
