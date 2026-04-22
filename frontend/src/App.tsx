import { Route, Routes } from "react-router-dom";
import Overview from "./pages/Overview";
import GraphPage from "./pages/GraphPage";
import SearchPage from "./pages/SearchPage";
import AnalysisPage from "./pages/AnalysisPage";
import SymbolPage from "./pages/SymbolPage";
import DiffPage from "./pages/DiffPage";
import SettingsPage from "./pages/SettingsPage";
import { Layout } from "./components/Layout";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/diff" element={<DiffPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/symbol/:id" element={<SymbolPage />} />
      </Routes>
    </Layout>
  );
}
