import { NavLink, Route, Routes } from "react-router-dom";
import Overview from "./pages/Overview";
import GraphPage from "./pages/GraphPage";
import SearchPage from "./pages/SearchPage";
import AnalysisPage from "./pages/AnalysisPage";
import SymbolPage from "./pages/SymbolPage";

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        "px-3 py-1.5 rounded-md text-sm transition-colors " +
        (isActive
          ? "bg-accent/20 text-accent border border-accent"
          : "text-slate-400 hover:text-slate-100")
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-border bg-panel/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-accent/20 border border-accent" />
            <span className="font-bold">CodeAtlas</span>
            <span className="text-xs text-slate-500">v1.0</span>
          </div>
          <nav className="flex items-center gap-1 ml-4">
            <NavItem to="/" label="Overview" />
            <NavItem to="/graph" label="Graph" />
            <NavItem to="/search" label="Search" />
            <NavItem to="/analysis" label="Analysis" />
          </nav>
          <div className="ml-auto text-xs text-slate-500">
            <a
              href="https://github.com/AryanSaini26/CodeAtlas"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
            </a>
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/symbol/:id" element={<SymbolPage />} />
        </Routes>
      </main>
    </div>
  );
}
