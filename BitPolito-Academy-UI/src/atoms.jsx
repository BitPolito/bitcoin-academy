// Shared atoms for BitPolito Academy.

const { useState, useEffect, useRef, useMemo } = React;

// --- Brand monogram (the pixelated bitpolito glyph), simplified to "BP·A"
function BrandMark({ className = "" }) {
  return (
    <a href="#" onClick={(e) => { e.preventDefault(); window.__nav && window.__nav("home"); }}
       className={`inline-flex items-center gap-3 ${className}`}>
      {/* Bit-pixel logo (simplified) */}
      <svg viewBox="0 0 36 24" className="w-9 h-6 ink" fill="currentColor" aria-hidden>
        <rect x="0"  y="2"  width="2" height="14"/>
        <rect x="2"  y="0"  width="2" height="2"/>
        <rect x="4"  y="2"  width="2" height="2"/>
        <rect x="6"  y="4"  width="2" height="14"/>
        <rect x="4"  y="14" width="2" height="2"/>
        <rect x="2"  y="16" width="2" height="2"/>
        <rect x="10" y="6"  width="2" height="12"/>
        <rect x="12" y="4"  width="2" height="2"/>
        <rect x="14" y="6"  width="2" height="6"/>
        <rect x="12" y="12" width="2" height="2"/>
        <rect x="20" y="2"  width="2" height="20"/>
        <rect x="22" y="0"  width="2" height="2"/>
        <rect x="22" y="22" width="2" height="2"/>
        <rect x="28" y="6"  width="2" height="12"/>
        <rect x="30" y="4"  width="2" height="2"/>
        <rect x="32" y="6"  width="2" height="12"/>
        <rect x="30" y="18" width="2" height="2"/>
      </svg>
      <span className="font-mono text-[11px] tracking-[0.18em] uppercase ink font-semibold">
        BitPolito · Academy
      </span>
    </a>
  );
}

// --- Status chip
function StatusChip({ state, progress }) {
  const map = {
    queued:     { dot: "#7a7f9a", label: "queued",      ring: "#7a7f9a" },
    uploading:  { dot: "#a55a00", label: "uploading",   ring: "#a55a00" },
    uploaded:   { dot: "#1a7f3a", label: "uploaded",    ring: "#1a7f3a" },
    processing: { dot: "#a55a00", label: "processing",  ring: "#a55a00" },
    indexed:    { dot: "#1a7f3a", label: "indexed",     ring: "#1a7f3a" },
    failed:     { dot: "#b3261e", label: "failed",      ring: "#b3261e" },
  };
  const m = map[state] || map.queued;
  const animated = state === "processing" || state === "uploading";
  return (
    <span className="chip" style={{
      color: m.dot,
      borderColor: m.ring,
      border: "1px solid",
      background: "transparent",
    }}>
      <span className={"inline-block w-1.5 h-1.5 rounded-full " + (animated ? "dotpulse" : "")}
            style={{ background: m.dot }} />
      {m.label}
      {animated && progress != null
        ? <span className="mono">{Math.round(progress * 100)}%</span>
        : null}
    </span>
  );
}

// --- Striped placeholder (used for course covers, slide thumbnails, figures)
function Stripes({ label, className = "", aspect = "16/10" }) {
  return (
    <div className={`stripes b-thin-1 relative overflow-hidden ${className}`}
         style={{ aspectRatio: aspect, border: "1px solid rgba(0,28,224,0.18)" }}>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-60">
          {label}
        </span>
      </div>
      <div className="absolute top-1.5 left-1.5 w-2 h-2 border-l border-t border-current opacity-60" />
      <div className="absolute top-1.5 right-1.5 w-2 h-2 border-r border-t border-current opacity-60" />
      <div className="absolute bottom-1.5 left-1.5 w-2 h-2 border-l border-b border-current opacity-60" />
      <div className="absolute bottom-1.5 right-1.5 w-2 h-2 border-r border-b border-current opacity-60" />
    </div>
  );
}

// --- Section header (mono caption + rule)
function SectionHead({ left, right, className = "" }) {
  return (
    <div className={`flex items-end justify-between b-thin-b pb-1.5 mb-3 ${className}`}>
      <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
        {left}
      </div>
      {right ? <div className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-60">{right}</div> : null}
    </div>
  );
}

// --- Thin progress bar
function ProgressBar({ value = 0, animated = true }) {
  return (
    <div className="w-full h-1.5 b-thin-1 overflow-hidden"
         style={{ border: "1px solid rgba(0,28,224,0.25)", background: "transparent" }}>
      <div className={"h-full " + (animated ? "bar-stripes" : "")}
           style={{ width: `${Math.round(value * 100)}%`, background: "#001CE0", transition: "width 0.3s ease" }} />
    </div>
  );
}

// --- Top app bar
function TopBar({ active, onNav, dark, onToggleDark }) {
  const tabs = [
    { id: "home",      label: "Courses" },
    { id: "workspace", label: "Workspace" },
    { id: "source",    label: "Source" },
    { id: "study",     label: "Study" },
  ];
  return (
    <header className="sticky top-0 z-40 bg-surface dark:bg-blue-dark b-thin-b">
      <div className="max-w-[1480px] mx-auto px-6 h-14 flex items-center gap-8">
        <BrandMark />
        <nav className="flex items-center gap-1 ml-4">
          {tabs.map(t => (
            <button key={t.id}
              onClick={() => onNav(t.id)}
              className={"px-3 h-8 rounded-md font-mono text-[11px] tracking-[0.14em] uppercase whitespace-nowrap transition-all " +
                (active === t.id
                  ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark"
                  : "hover:bg-blue-dark/5 dark:hover:bg-white/10")}>
              {t.label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden md:flex items-center gap-2 px-3 h-8 b-thin rounded-md w-72">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 opacity-60" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
            </svg>
            <span className="font-mono text-[11px] opacity-60">Search courses, docs, passages…</span>
            <span className="ml-auto mono text-[10px] opacity-50 b-thin px-1.5 rounded">⌘K</span>
          </div>
          <button onClick={onToggleDark}
            className="h-8 w-8 b-thin rounded-md flex items-center justify-center hover:bg-blue-dark/5 dark:hover:bg-white/10"
            title="Toggle theme">
            {dark
              ? <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor"><circle cx="12" cy="12" r="4"/><g stroke="currentColor" strokeWidth="2"><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><line x1="4.5" y1="4.5" x2="6.5" y2="6.5"/><line x1="17.5" y1="17.5" x2="19.5" y2="19.5"/><line x1="4.5" y1="19.5" x2="6.5" y2="17.5"/><line x1="17.5" y1="6.5" x2="19.5" y2="4.5"/></g></svg>
              : <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor"><path d="M21 12.8A9 9 0 0 1 11.2 3a7 7 0 1 0 9.8 9.8z"/></svg>}
          </button>
          <div className="h-8 w-8 b-thin rounded-md flex items-center justify-center font-mono text-[11px] font-semibold">
            LC
          </div>
        </div>
      </div>
    </header>
  );
}

// --- Breadcrumb
function Crumbs({ items }) {
  return (
    <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] uppercase opacity-70">
      {items.map((it, i) => (
        <React.Fragment key={i}>
          {i > 0 ? <span className="opacity-40">/</span> : null}
          <span className={i === items.length - 1 ? "opacity-100 font-semibold" : ""}>{it}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

// --- Empty / error / loading micro-states
function EmptyBlock({ title, sub, action }) {
  return (
    <div className="b-hard rounded-lg p-10 text-center bg-white dark:bg-blue-dark">
      <div className="mx-auto w-10 h-10 b-thin-1 rounded-md mb-4 stripes" style={{border:"1px solid currentColor"}}/>
      <div className="font-medium text-lg">{title}</div>
      <div className="opacity-70 text-sm mt-1">{sub}</div>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

// --- Citation pill (inline, hoverable)
function Cite({ id, children, onHover, onClick, active }) {
  return (
    <span onMouseEnter={() => onHover && onHover(id)}
          onMouseLeave={() => onHover && onHover(null)}
          onClick={() => onClick && onClick(id)}
          className={"inline cursor-pointer transition-colors " + (active ? "cite-hl" : "")}
          style={{ borderBottom: "1px dashed currentColor", paddingBottom: "1px" }}>
      {children}
      <sup className="font-mono text-[9px] opacity-70 ml-0.5">[{id.replace("ev-", "")}]</sup>
    </span>
  );
}

Object.assign(window, { BrandMark, StatusChip, Stripes, SectionHead, ProgressBar, TopBar, Crumbs, EmptyBlock, Cite });
