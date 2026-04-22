import { useEffect } from "react";

type Shortcut = { keys: string[]; label: string };

const SHORTCUTS: { group: string; items: Shortcut[] }[] = [
  {
    group: "Navigation",
    items: [
      { keys: ["⌘", "K"], label: "Open command palette" },
      { keys: ["Ctrl", "K"], label: "Open command palette (Windows / Linux)" },
      { keys: ["↑", "↓"], label: "Move selection in palette" },
      { keys: ["↵"], label: "Open highlighted result" },
      { keys: ["Esc"], label: "Close modal / palette" },
    ],
  },
  {
    group: "Help",
    items: [
      { keys: ["?"], label: "Show this cheatsheet" },
    ],
  },
];

export function ShortcutsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh] px-4 animate-fade-up"
      style={{ backgroundColor: "rgba(5,5,5,0.75)" }}
      onClick={onClose}
    >
      <div
        className="glass rounded-[12px] w-full max-w-[520px] flex flex-col overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="font-head font-bold text-[14px] text-text-1">
            Keyboard shortcuts
          </div>
          <kbd className="kbd">esc</kbd>
        </div>
        <div className="px-4 py-3 flex flex-col gap-4 max-h-[70vh] overflow-y-auto">
          {SHORTCUTS.map((g) => (
            <div key={g.group}>
              <div className="text-[10px] text-text-4 uppercase tracking-[0.06em] mb-2">
                {g.group}
              </div>
              <div className="flex flex-col gap-1.5">
                {g.items.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="text-[12px] text-text-2">{item.label}</span>
                    <div className="flex items-center gap-1">
                      {item.keys.map((k) => (
                        <kbd key={k} className="kbd">
                          {k}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
