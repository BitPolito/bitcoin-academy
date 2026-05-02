// App shell — routing, dark mode, tweaks panel.

const { useState: _u4, useEffect: _e4 } = React;

const TWEAK_DEFAULS = /*EDITMODE-BEGIN*/{
  "studyLayout": "split",
  "density": "comfortable",
  "showInspect": true,
  "accent": "blue"
}/*EDITMODE-END*/;

function App() {
  const [route, setRoute] = _u4("home");
  const [dark, setDark]   = _u4(false);
  const tk = (window.useTweaks || (() => [TWEAK_DEFAULS, () => {}]))(TWEAK_DEFAULS);
  const [tweaks, setTweak] = tk;

  _e4(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  // Density
  _e4(() => {
    const r = document.documentElement;
    if (tweaks.density === "compact") r.style.fontSize = "14.5px";
    else r.style.fontSize = "16px";
  }, [tweaks.density]);

  window.__nav = setRoute;

  let screen;
  if (route === "home")        screen = <CoursesScreen onOpenCourse={() => setRoute("workspace")} onCreate={() => setRoute("workspace")} />;
  else if (route === "workspace") screen = <WorkspaceScreen onOpenDoc={() => setRoute("source")} onStartStudy={() => setRoute("study")} />;
  else if (route === "source")    screen = <SourceViewer onStartStudy={() => setRoute("study")} />;
  else if (route === "study")     screen = <StudyScreen layoutVariant={tweaks.studyLayout} />;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar active={route} onNav={setRoute} dark={dark} onToggleDark={() => setDark(d => !d)} />
      <main className="flex-1">{screen}</main>
      <footer className="b-thin-t mt-10">
        <div className="max-w-[1480px] mx-auto px-6 py-5 flex items-center gap-6 font-mono text-[11px] opacity-70">
          <span>BitPolito · Academy</span>
          <span>local-first · open-source</span>
          <span>built on qvac SDK</span>
          <span className="ml-auto">v0.1 · MVP preview</span>
        </div>
      </footer>

      {window.TweaksPanel ? (
        <TweaksPanel title="Tweaks">
          <TweakSection title="Study layout">
            <TweakRadio
              value={tweaks.studyLayout}
              options={[
                { value: "split", label: "Split · source ↔ output" },
                { value: "power", label: "Power · output ↔ source" },
              ]}
              onChange={(v) => setTweak("studyLayout", v)}
            />
            <p className="mono text-[10px] opacity-70 mt-2">
              Split is recommended for the MVP — most students read source first, output second.
              Power flips the order for users who think output-first.
            </p>
          </TweakSection>
          <TweakSection title="Density">
            <TweakRadio value={tweaks.density}
              options={[{value:"comfortable", label:"Comfortable"}, {value:"compact", label:"Compact"}]}
              onChange={(v) => setTweak("density", v)} />
          </TweakSection>
          <TweakSection title="Theme">
            <TweakToggle value={dark} onChange={(v) => setDark(v)} label="Dark mode" />
          </TweakSection>
          <TweakSection title="Quick jump">
            <div className="flex flex-col gap-2">
              <TweakButton label="→ Courses"        onClick={() => setRoute("home")} />
              <TweakButton label="→ Workspace"      onClick={() => setRoute("workspace")} />
              <TweakButton label="→ Source viewer"  onClick={() => setRoute("source")} />
              <TweakButton label="→ Study"          onClick={() => setRoute("study")} />
            </div>
          </TweakSection>
        </TweaksPanel>
      ) : null}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
