// Courses screen (Home) + course-creation modal.

const { useState: _u1 } = React;

function CoursesScreen({ onOpenCourse, onCreate }) {
  const D = window.ACADEMY_DATA;
  const [creating, setCreating] = _u1(false);
  const [filter, setFilter] = _u1("all"); // all | active | archived

  const courses = D.courses;

  return (
    <div className="page-fade max-w-[1480px] mx-auto px-6 py-8">
      {/* Hero head */}
      <div className="grid grid-cols-12 gap-6 mb-10">
        <div className="col-span-12 lg:col-span-8">
          <Crumbs items={["Academy", "Courses"]} />
          <h1 className="text-5xl lg:text-6xl font-medium tracking-tight leading-[1.05] mt-6 mb-5">
            Study, grounded in your<br/>own course material.
          </h1>
          <p className="text-lg leading-relaxed max-w-[58ch] opacity-80">
            Each course is an isolated workspace. Drop in slides, notes, textbooks
            and past exams — Academy parses, indexes and keeps every generated answer
            anchored to its exact source.
          </p>
          <div className="flex items-center gap-3 mt-6">
            <button className="btn-primary" onClick={() => setCreating(true)}>
              <span className="mono text-[14px] leading-none">+</span> Create course
            </button>
            <button className="btn-ghost">Import from Polito portal</button>
            <span className="ml-2 font-mono text-[11px] opacity-60">
              5 courses · 62 documents · 1.4k chunks indexed
            </span>
          </div>
        </div>

        {/* Right: status snapshot */}
        <div className="col-span-12 lg:col-span-4">
          <div className="b-hard rounded-lg p-5 bg-white dark:bg-blue-dark/40 tick-corners">
            <SectionHead left="Local index · last 24h" right="qvac · v0.4.2" />
            <div className="grid grid-cols-2 gap-3 mono">
              <Stat n="62"   k="documents" />
              <Stat n="1,438" k="chunks"   />
              <Stat n="5"    k="courses"   />
              <Stat n="3"    k="processing" warn />
            </div>
            <div className="mt-4 pt-4 b-thin-t flex items-center justify-between">
              <span className="font-mono text-[11px] opacity-70">Local-first · all data on device</span>
              <span className="font-mono text-[10px] tracking-[0.2em] uppercase">v0.1 MVP</span>
            </div>
          </div>
        </div>
      </div>

      {/* Filter rail */}
      <div className="flex items-center gap-2 mb-4">
        {[
          { id: "all", label: "All", n: 5 },
          { id: "active", label: "Active term", n: 3 },
          { id: "archived", label: "Archived", n: 2 },
        ].map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={"font-mono text-[11px] tracking-[0.18em] uppercase px-3 h-8 rounded-md transition-all " +
              (filter === f.id ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark" : "b-thin")}>
            {f.label} <span className="opacity-60 ml-1">{f.n}</span>
          </button>
        ))}
        <div className="ml-auto font-mono text-[11px] opacity-60">sorted · last touched</div>
      </div>

      {/* Course grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {courses.map(c => <CourseCard key={c.id} c={c} onOpen={() => onOpenCourse(c.id)} />)}
        <button onClick={() => setCreating(true)}
          className="b-hard rounded-lg p-6 stripes hover-card flex flex-col items-center justify-center min-h-[238px] text-center">
          <div className="font-mono text-3xl leading-none mb-2">+</div>
          <div className="font-medium">Create new course</div>
          <div className="font-mono text-[11px] opacity-70 mt-1">⌘N</div>
        </button>
      </div>

      {creating ? <CreateCourseModal onClose={() => setCreating(false)} onCreate={onCreate} /> : null}
    </div>
  );
}

function Stat({ n, k, warn }) {
  return (
    <div className="b-thin rounded-md p-3">
      <div className={"text-2xl font-medium tnum " + (warn ? "text-warn" : "")}>{n}</div>
      <div className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70 mt-1">{k}</div>
    </div>
  );
}

function CourseCard({ c, onOpen }) {
  const totalState =
    c.failed > 0     ? { dot: "#b3261e", label: c.failed + " failed" }
    : c.processing>0 ? { dot: "#a55a00", label: c.processing + " processing" }
    : { dot: "#1a7f3a", label: "all indexed" };

  return (
    <div onClick={onOpen}
         className="b-hard rounded-lg p-5 bg-white dark:bg-blue-dark/30 hover-card cursor-pointer">
      <div className="flex items-center justify-between mb-3">
        <span className="mono text-[10px] tracking-[0.2em] uppercase opacity-70">{c.code}</span>
        {c.pinned ? <span className="mono text-[10px] tracking-[0.2em] uppercase opacity-70">PINNED</span> : null}
      </div>
      <Stripes label={c.code} className="mb-4 rounded-md" aspect="16/7" />
      <h3 className="text-lg font-medium leading-snug mb-1">{c.title}</h3>
      <div className="font-mono text-[11px] opacity-70 mb-4">
        {c.term} · {c.lecturer}
      </div>

      <div className="grid grid-cols-3 gap-2 mb-4">
        <Mini n={c.docs}     k="docs" />
        <Mini n={c.indexed}  k="indexed" />
        <Mini n={c.processing + c.failed} k="open" warn={c.failed > 0 || c.processing > 0} />
      </div>

      <div className="flex items-center justify-between b-thin-t pt-3">
        <span className="font-mono text-[11px] flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full" style={{background: totalState.dot}} />
          {totalState.label}
        </span>
        <span className="font-mono text-[11px] opacity-70">{c.lastTouched}</span>
      </div>
    </div>
  );
}

function Mini({ n, k, warn }) {
  return (
    <div className="text-center">
      <div className={"text-xl tnum font-medium " + (warn ? "text-warn" : "")}>{n}</div>
      <div className="font-mono text-[9px] tracking-[0.18em] uppercase opacity-70">{k}</div>
    </div>
  );
}

function CreateCourseModal({ onClose, onCreate }) {
  const [title, setTitle] = _u1("");
  const [code, setCode]   = _u1("");
  const [term, setTerm]   = _u1("2025/26 · Sem II");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
         style={{ background: "rgba(0,28,224,0.18)" }}
         onClick={onClose}>
      <div className="b-hard rounded-lg bg-white dark:bg-blue-dark w-full max-w-xl p-7"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <Crumbs items={["Courses", "New"]} />
          <button onClick={onClose} className="font-mono text-[14px] opacity-70">×</button>
        </div>
        <h2 className="text-2xl font-medium mb-1">Create a course workspace</h2>
        <p className="opacity-75 text-sm mb-6">
          A course is a sealed bucket — its documents, embeddings and outputs never bleed into
          other courses.
        </p>

        <div className="grid grid-cols-1 gap-4 mb-5">
          <Field label="Course title" hint="e.g. Information Theory & Coding">
            <input value={title} onChange={e => setTitle(e.target.value)}
              className="w-full h-10 px-3 b-hard-1 rounded-md bg-transparent outline-none focus:bg-blue-dark/5 dark:focus:bg-white/10"
              placeholder="Information Theory & Coding" />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Polito code" hint="optional">
              <input value={code} onChange={e => setCode(e.target.value)}
                className="w-full h-10 px-3 b-hard-1 rounded-md bg-transparent mono outline-none focus:bg-blue-dark/5 dark:focus:bg-white/10"
                placeholder="01TWZSM" />
            </Field>
            <Field label="Term">
              <select value={term} onChange={e => setTerm(e.target.value)}
                className="w-full h-10 px-3 b-hard-1 rounded-md bg-transparent mono">
                <option>2025/26 · Sem II</option>
                <option>2025/26 · Sem I</option>
                <option>2024/25 · Sem II</option>
              </select>
            </Field>
          </div>
        </div>

        <div className="flex items-center justify-between b-thin-t pt-4">
          <span className="font-mono text-[11px] opacity-70">
            ▢  Use empty workspace · ▣ Clone settings from another course
          </span>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn-primary" onClick={() => { onCreate(title || "Untitled course"); onClose(); }}>
              Create workspace →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="font-mono text-[10px] tracking-[0.2em] uppercase opacity-80">{label}</span>
        {hint ? <span className="font-mono text-[10px] opacity-50">{hint}</span> : null}
      </div>
      {children}
    </label>
  );
}

Object.assign(window, { CoursesScreen, CourseCard, CreateCourseModal });
