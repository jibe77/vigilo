import { useEffect, useRef, useState } from "react";

export type ReportFormat = "markdown" | "docx" | "pdf";

const LABELS: Record<ReportFormat, string> = {
  markdown: "Markdown",
  docx: "Docx",
  pdf: "PDF",
};

/**
 * "Download as …" split button: the current format downloads on click, the
 * chevron opens the format list. Docx/PDF are rendered by the API on demand,
 * so a menu item may take a second on the Pi — the trigger shows progress.
 */
export function ReportDownloadMenu({
  onDownload,
  disabled,
}: {
  onDownload: (format: ReportFormat) => Promise<void>;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const [current, setCurrent] = useState<ReportFormat>("markdown");
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape — the menu is absolutely positioned.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function run(format: ReportFormat) {
    setOpen(false);
    setBusy(format);
    try {
      await onDownload(format);
      setCurrent(format);
    } finally {
      setBusy(null);
    }
  }

  const label = busy ? `Preparing ${LABELS[busy]}…` : `Download as ${LABELS[current]}`;

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        className="btn-ghost-sm rounded-r-none border-r-0"
        disabled={disabled || busy !== null}
        onClick={() => void run(current)}
        title={`Download the report as ${LABELS[current]}`}
      >
        {label}
      </button>
      <button
        className="btn-ghost-sm rounded-l-none px-2"
        disabled={disabled || busy !== null}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Choose download format"
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
          <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
      {open && (
        <ul
          role="menu"
          className="absolute right-0 top-full z-20 mt-1 min-w-[10rem] overflow-hidden rounded-md border border-line bg-surface py-1 text-xs shadow-card"
        >
          {(Object.keys(LABELS) as ReportFormat[]).map((format) => (
            <li key={format} role="none">
              <button
                role="menuitem"
                className={`block w-full px-3 py-1.5 text-left hover:bg-canvas ${
                  format === current ? "font-semibold text-accent" : "text-ink"
                }`}
                onClick={() => void run(format)}
              >
                {LABELS[format]}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
