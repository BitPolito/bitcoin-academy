// Course workspace + Source viewer.

const { useState: _u2 } = React;

function WorkspaceScreen({ onOpenDoc, onStartStudy }) {
  const D = window.ACADEMY_DATA;
  const [docs, setDocs] = _u2(D.documents);
  const [selected, setSelected] = _u2(docs[0].id);
  const [filter, setFilter] = _u2("all");
  const [dragOver, setDragOver] = _u2(false);

  // Light simulation of upload progress on load
  React.useEffect(() => {
    const t = setInterval(() => {
      setDocs(prev => prev.map(d => {
        if (d.state === "uploading" && d.progress < 1) {
          const next = Math.min(1, (d.progress || 0) + 0.07);
          return next >= 1 ? { ...d, state: "processing", progress: 0.05, stage: "parse → chunk" } : { ...d, progress: next };
        }
        if (d.state === "processing" && d.progress < 1) {
          const next = Math.min(1, (d.progress || 0) + 0.04);
          return next >= 1
            ? { ...d, state: "indexed", progress: 1, chunks: 200 + Math.round(Math.random() * 200), parser: { ok: 0.95, ocr: false, lang: "en" } }
            : { ...d, progress: next };
        }
        return d;
      }));
    }, 700);
    return () => clearInterval(t);
  }, []);

  const filtered = docs.filter(d => {
    if (filter === "all") return true;
    if (filter === "open") return d.state !== "indexed";
    return d.state === filter;
  });
  const sel = docs.find(d => d.id === selected) || docs[0];

  const handleRetry = (id) => setDocs(prev => prev.map(d => d.id === id ? { ...d, state: "uploading", progress: 0.1, error: null } : d));
  const handleClear = (id) => setDocs(prev => prev.filter(d => d.id !== id));

  // Course header summary
  const c = D.courses[0];
  const counts = {
    indexed:    docs.filter(d => d.state === "indexed").length,
    processing: docs.filter(d => d.state === "processing" || d.state === "uploading").length,
    failed:     docs.filter(d => d.state === "failed").length,
  };

  return (
    <div className="page-fade max-w-[1480px] mx-auto px-6 py-6">
      {/* Course header */}
      <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 px-6 py-5 mb-5 flex items-start gap-6">
        <div className="flex-1 min-w-0">
          <Crumbs items={["Academy", "Courses", c.title]} />
          <div className="flex items-baseline gap-3 mt-3">
            <span className="mono text-[11px] tracking-[0.2em] uppercase opacity-70">{c.code}</span>
            <h1 className="text-3xl font-medium leading-tight">{c.title}</h1>
          </div>
          <div className="font-mono text-[11px] opacity-70 mt-1">{c.term} · {c.lecturer}</div>
        </div>
        <div className="flex items-center gap-6 b-thin-l pl-6">
          <Stat2 n={docs.length} k="documents" />
          <Stat2 n={counts.indexed} k="indexed" />
          <Stat2 n={counts.processing} k="processing" warn={counts.processing>0} />
          <Stat2 n={counts.failed} k="failed" err={counts.failed>0} />
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" onClick={() => onOpenDoc(sel.id)}>Open viewer</button>
          <button className="btn-primary" onClick={() => onStartStudy()}>
            <span>Study →</span>
          </button>
        </div>
      </div>

      {/* Two columns */}
      <div className="grid grid-cols-12 gap-5">
        {/* LEFT — upload + document list */}
        <div className="col-span-12 lg:col-span-7 space-y-5">
          <div
            className={"b-hard rounded-lg p-5 transition-all " + (dragOver ? "bg-blue-dark/5 dark:bg-white/10" : "bg-white dark:bg-blue-dark/30")}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault(); setDragOver(false);
              const fakeName = "Drop_" + (docs.length+1) + ".pdf";
              setDocs(prev => [...prev, {
                id: "doc-" + Date.now(), name: fakeName, kind: "slides",
                pages: 20, sizeKB: 1800, uploadedAt: "now", state: "uploading", progress: 0.05,
              }]);
            }}>
            <SectionHead left="Upload · drop or click" right="PDF · PPTX · MD · TXT · ≤ 50 MB" />
            <div className="flex items-center gap-5">
              <div className="w-16 h-16 b-thin-1 rounded-md stripes flex items-center justify-center"
                   style={{border: "1px solid currentColor"}}>
                <span className="font-mono text-2xl leading-none">↑</span>
              </div>
              <div className="flex-1">
                <div className="font-medium">Drop files here, or paste a URL</div>
                <div className="font-mono text-[11px] opacity-70 mt-1">
                  Files are parsed locally · structure-preserving · embedded with qvac
                </div>
              </div>
              <button className="btn-primary" onClick={() => {
                setDocs(prev => [...prev, {
                  id: "doc-" + Date.now(), name: "Lecture-supplement-" + (prev.length+1) + ".pdf", kind: "slides",
                  pages: 20, sizeKB: 1800, uploadedAt: "now", state: "uploading", progress: 0.1
                }]);
              }}>Choose files</button>
            </div>
          </div>

          {/* Filter bar */}
          <div className="flex items-center gap-2">
            {[
              { id: "all", label: "All" },
              { id: "indexed", label: "Indexed" },
              { id: "processing", label: "Processing" },
              { id: "failed", label: "Failed" },
              { id: "open", label: "Open · needs attention" },
            ].map(f => (
              <button key={f.id} onClick={() => setFilter(f.id)}
                className={"font-mono text-[11px] tracking-[0.18em] uppercase px-3 h-8 rounded-md transition-all " +
                  (filter === f.id ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark" : "b-thin")}>
                {f.label}
              </button>
            ))}
            <span className="ml-auto font-mono text-[11px] opacity-60">{filtered.length} shown</span>
          </div>

          {/* Document list */}
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 overflow-hidden">
            <div className="grid grid-cols-[1fr_120px_120px_140px_30px] gap-3 px-4 py-2.5 b-thin-b font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">
              <div>Document</div>
              <div>Kind</div>
              <div>Size · pages</div>
              <div>Status</div>
              <div></div>
            </div>
            {filtered.map(d => (
              <DocRow key={d.id} d={d}
                      selected={d.id === selected}
                      onSelect={() => setSelected(d.id)}
                      onOpen={() => onOpenDoc(d.id)}
                      onRetry={() => handleRetry(d.id)}
                      onClear={() => handleClear(d.id)} />
            ))}
            {filtered.length === 0 ? (
              <div className="p-10 text-center font-mono text-[11px] opacity-60">No documents in this view.</div>
            ) : null}
          </div>
        </div>

        {/* RIGHT — document detail panel */}
        <div className="col-span-12 lg:col-span-5">
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 sticky top-20">
            <div className="px-5 py-4 b-thin-b">
              <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-1">Document detail</div>
              <h3 className="font-medium leading-tight">{sel.name}</h3>
              <div className="font-mono text-[11px] opacity-70 mt-1">
                {sel.kind} · {sel.pages || "—"} pages · {(sel.sizeKB/1024).toFixed(1)} MB · {sel.uploadedAt}
              </div>
            </div>

            <div className="p-5 space-y-5">
              <div>
                <SectionHead left="Lifecycle" />
                <Lifecycle state={sel.state} progress={sel.progress} />
                {sel.stage ? <div className="font-mono text-[11px] opacity-70 mt-2">stage · {sel.stage}</div> : null}
              </div>

              {sel.state === "failed" ? (
                <div className="b-hard-1 rounded-md p-3" style={{borderColor: "#b3261e", color:"#b3261e"}}>
                  <div className="font-mono text-[10px] tracking-[0.2em] uppercase mb-1">Error</div>
                  <div className="font-mono text-[12px] leading-relaxed">{sel.error}</div>
                  <div className="flex gap-2 mt-3">
                    <button className="btn-ghost" style={{borderColor: "#b3261e", color: "#b3261e"}} onClick={() => handleRetry(sel.id)}>Retry parse</button>
                    <button className="btn-ghost" style={{borderColor: "#b3261e", color: "#b3261e"}} onClick={() => handleClear(sel.id)}>Clear</button>
                  </div>
                </div>
              ) : null}

              {sel.parser ? (
                <div>
                  <SectionHead left="Parser quality" right={(sel.parser.ok*100).toFixed(0) + "% confident"} />
                  <div className="grid grid-cols-3 gap-2">
                    <KV k="lang"   v={sel.parser.lang.toUpperCase()} />
                    <KV k="ocr"    v={sel.parser.ocr ? "on" : "off"} />
                    <KV k="chunks" v={sel.chunks ?? "—"} />
                  </div>
                </div>
              ) : null}

              <div>
                <SectionHead left="Parsed structure preview" right="slide 17 / 42" />
                <ParsedPreview />
              </div>

              <div className="flex items-center gap-2 b-thin-t pt-4">
                <button className="btn-ghost" onClick={() => onOpenDoc(sel.id)}>Open in viewer →</button>
                <button className="btn-primary" onClick={onStartStudy}>Use in study</button>
                <span className="ml-auto font-mono text-[10px] opacity-60">id · {sel.id}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat2({ n, k, warn, err }) {
  const cls = err ? "text-err" : warn ? "text-warn" : "";
  return (
    <div className="text-center">
      <div className={"text-xl tnum font-medium " + cls}>{n}</div>
      <div className="font-mono text-[9px] tracking-[0.18em] uppercase opacity-70">{k}</div>
    </div>
  );
}

function KV({ k, v }) {
  return (
    <div className="b-thin rounded-md p-2">
      <div className="font-mono text-[9px] tracking-[0.2em] uppercase opacity-60">{k}</div>
      <div className="font-mono text-[12px] mt-0.5">{v}</div>
    </div>
  );
}

function DocRow({ d, selected, onSelect, onOpen, onRetry, onClear }) {
  return (
    <div onClick={onSelect}
         className={"grid grid-cols-[1fr_120px_120px_140px_30px] gap-3 px-4 py-3 b-thin-b items-center cursor-pointer transition-colors " +
           (selected ? "bg-blue-dark/8 dark:bg-white/10" : "hover:bg-blue-dark/5 dark:hover:bg-white/5")}>
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-10 b-thin-1 stripes flex-shrink-0 rounded-sm" style={{border:"1px solid currentColor"}}/>
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{d.name}</div>
          <div className="font-mono text-[10px] opacity-60 mt-0.5">
            {d.uploadedAt} · {d.parser ? `${d.parser.lang} · ${d.parser.ocr ? "OCR" : "native"}` : "queued"}
          </div>
        </div>
      </div>
      <div className="font-mono text-[11px] opacity-80">{d.kind}</div>
      <div className="font-mono text-[11px] opacity-80 tnum">
        {(d.sizeKB/1024).toFixed(1)} MB · {d.pages || "—"}p
      </div>
      <div className="flex flex-col gap-1">
        <StatusChip state={d.state} progress={d.progress} />
        {(d.state === "uploading" || d.state === "processing") && d.progress != null
          ? <ProgressBar value={d.progress} animated /> : null}
      </div>
      <button onClick={(e) => { e.stopPropagation(); onOpen(); }}
              className="font-mono text-sm opacity-60 hover:opacity-100">→</button>
    </div>
  );
}

function Lifecycle({ state, progress }) {
  const stages = ["queued", "uploading", "processing", "indexed"];
  const failed = state === "failed";
  const idx = failed ? -1 : stages.indexOf(state === "uploaded" ? "processing" : state);
  return (
    <div className="flex items-center gap-1.5">
      {stages.map((s, i) => {
        const done = !failed && i < idx;
        const here = !failed && i === idx;
        return (
          <React.Fragment key={s}>
            <div className={"flex-1 h-7 b-thin-1 rounded-sm flex items-center justify-center font-mono text-[10px] tracking-[0.16em] uppercase " +
              (failed ? "" : done ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark" : here ? "" : "opacity-40")}
              style={{ border: "1px solid currentColor", position: "relative", overflow: "hidden" }}>
              {here && progress != null
                ? <div className="absolute inset-0 bar-stripes" style={{ width: `${Math.round(progress*100)}%`, background: "#001CE0", opacity: 0.85 }} />
                : null}
              <span className="relative z-10" style={here ? {color:"#fff"} : {}}>{s}</span>
            </div>
            {i < stages.length - 1 ? <span className="opacity-40 mono text-[10px]">›</span> : null}
          </React.Fragment>
        );
      })}
      {failed ? <span className="ml-2 chip" style={{color:"#b3261e", border:"1px solid #b3261e"}}>FAILED</span> : null}
    </div>
  );
}

function ParsedPreview() {
  const D = window.ACADEMY_DATA;
  const p = D.openDoc.parsed;
  return (
    <div className="b-thin-1 rounded-md p-4 space-y-3" style={{border:"1px solid currentColor"}}>
      <div className="font-medium text-[15px] leading-snug">{p.title}</div>
      <ul className="space-y-1.5 text-[12.5px] leading-relaxed opacity-90 list-disc pl-5">
        {p.bullets.slice(0, 2).map((b, i) => <li key={i}>{b}</li>)}
      </ul>
      <div className="font-mono text-[12px] b-thin-1 rounded-sm px-3 py-2 inline-block"
           style={{border:"1px solid currentColor"}}>{p.formula}</div>
    </div>
  );
}

// =================== Source Viewer ===================

function SourceViewer({ onStartStudy }) {
  const D = window.ACADEMY_DATA;
  const doc = D.openDoc;
  const [page, setPage] = _u2(doc.activePage);
  const [hovered, setHovered] = _u2(null);

  return (
    <div className="page-fade max-w-[1480px] mx-auto px-6 py-5">
      {/* Doc header */}
      <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 px-5 py-3 mb-4 flex items-center gap-4">
        <Crumbs items={["Academy", "Info Theory", "Source viewer"]} />
        <div className="b-thin-l pl-4 ml-2 flex-1 min-w-0">
          <div className="font-medium truncate">{doc.name}</div>
          <div className="font-mono text-[11px] opacity-70">{doc.pages} pages · indexed · 318 chunks</div>
        </div>
        <div className="flex items-center gap-1 b-thin rounded-md">
          <button onClick={() => setPage(p => Math.max(1, p-1))} className="px-3 h-8 mono">‹</button>
          <span className="px-3 h-8 leading-8 font-mono text-[12px] tnum">page {page} / {doc.pages}</span>
          <button onClick={() => setPage(p => Math.min(doc.pages, p+1))} className="px-3 h-8 mono">›</button>
        </div>
        <button className="btn-primary" onClick={onStartStudy}>Use in study →</button>
      </div>

      {/* 3-pane: outline · viewer · meta */}
      <div className="grid grid-cols-12 gap-4" style={{minHeight: "calc(100vh - 220px)"}}>
        {/* Outline */}
        <aside className="col-span-12 lg:col-span-3 b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-4 ws-scroll overflow-auto">
          <SectionHead left="Outline" right={doc.outline.length + " sections"} />
          <ul className="space-y-1">
            {doc.outline.map(o => (
              <li key={o.id}>
                <button onClick={() => setPage(o.page)}
                  className={"w-full flex items-baseline gap-2 px-2 py-1.5 rounded-sm text-left text-[13px] " +
                    (page >= o.page && (o.page === doc.outline[doc.outline.length-1].page || page < (doc.outline[doc.outline.indexOf(o)+1]?.page ?? 999))
                      ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark" : "hover:bg-blue-dark/5 dark:hover:bg-white/10")}>
                  <span className="mono text-[10px] opacity-70 w-6">p.{o.page}</span>
                  <span className="leading-tight">{o.label}</span>
                </button>
              </li>
            ))}
          </ul>

          <div className="mt-6">
            <SectionHead left="Page thumbnails" />
            <div className="grid grid-cols-3 gap-2">
              {Array.from({length: 9}).map((_, i) => {
                const n = page - 4 + i;
                if (n < 1 || n > doc.pages) return <div key={i} />;
                return (
                  <button key={i} onClick={() => setPage(n)}
                    className={"b-thin-1 rounded-sm aspect-[3/4] stripes flex items-end justify-center pb-1 transition-all " +
                      (n === page ? "ring-2 ring-blue-dark dark:ring-white" : "")}
                    style={{border:"1px solid currentColor"}}>
                    <span className="mono text-[9px] opacity-70">{n}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        {/* Slide canvas */}
        <main className="col-span-12 lg:col-span-6 b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-6 ws-scroll overflow-auto">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Slide {page} · §4</div>
              <h2 className="text-2xl font-medium leading-tight mt-1">{doc.parsed.title}</h2>
            </div>
            <div className="font-mono text-[11px] opacity-70">parser · 97% · native</div>
          </div>

          <div className="b-thin-1 rounded-md p-6 stripes mb-5"
               style={{border:"1px solid currentColor", aspectRatio: "16/9"}}>
            <div className="bg-white dark:bg-blue-dark h-full rounded-sm p-6 flex flex-col">
              <div className="font-medium text-xl mb-4">{doc.parsed.title}</div>
              <ul className="space-y-3 flex-1">
                {doc.parsed.bullets.map((b, i) => (
                  <li key={i} className={"text-[13px] leading-relaxed flex gap-3 " + (i === 1 ? "cite-hl" : "")}>
                    <span className="mono opacity-60 mt-0.5">▸</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
              <div className="font-mono text-[14px] b-thin-1 rounded-sm px-3 py-2 self-start mt-3"
                   style={{border:"1px solid currentColor"}}>
                {doc.parsed.formula}
              </div>
              <div className="font-mono text-[10px] opacity-60 mt-3">{doc.parsed.cap}</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Anchor n="anchor #4.2" caption="Typical set definition" />
            <Anchor n="anchor #4.3" caption="Achievability sketch"  active />
            <Anchor n="anchor #4.4" caption="Converse forward-ref" />
          </div>
        </main>

        {/* Meta / structure */}
        <aside className="col-span-12 lg:col-span-3 space-y-4">
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-4">
            <SectionHead left="Parsed structure" />
            <div className="space-y-2 font-mono text-[11px]">
              <Tree label="title"     v="Source Coding Theorem" />
              <Tree label="bullets"   v="4 items · 312 tokens" />
              <Tree label="formula"   v="1 · LaTeX-recovered" />
              <Tree label="figure"    v="1 · raster · alt=auto" />
              <Tree label="anchors"   v="3 · stable IDs" />
            </div>
          </div>
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-4">
            <SectionHead left="Citations referencing this page" right="2" />
            <div className="space-y-2">
              {[D.evidence[0], D.evidence[2]].map(ev => (
                <div key={ev.id} className="b-thin rounded-md p-2.5">
                  <div className="font-mono text-[10px] opacity-70 mb-0.5">{ev.anchor} · score {ev.score.toFixed(2)}</div>
                  <div className="text-[12px] leading-snug opacity-90 line-clamp-2">{ev.preview}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-4">
            <SectionHead left="Quick actions" />
            <div className="flex flex-col gap-2">
              <button className="btn-ghost justify-start" onClick={onStartStudy}>Σ  Explain this slide</button>
              <button className="btn-ghost justify-start" onClick={onStartStudy}>?  Generate open questions</button>
              <button className="btn-ghost justify-start" onClick={onStartStudy}>◉  Oral exam on §4</button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Anchor({ n, caption, active }) {
  return (
    <div className={"b-thin-1 rounded-md p-3 " + (active ? "bg-blue-dark/8 dark:bg-white/10" : "")}
         style={{border:"1px solid currentColor"}}>
      <div className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">{n}</div>
      <div className="text-[12px] mt-1 leading-snug">{caption}</div>
    </div>
  );
}

function Tree({ label, v }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="opacity-50">└</span>
      <span className="opacity-70 w-16">{label}</span>
      <span className="opacity-100">{v}</span>
    </div>
  );
}

Object.assign(window, { WorkspaceScreen, SourceViewer });
