import { Link, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { EmptyState } from "./components/ui";
import CacheAnalysis from "./pages/CacheAnalysis";
import Compare from "./pages/Compare";
import ExperimentResults from "./pages/ExperimentResults";
import History from "./pages/History";
import Overview from "./pages/Overview";
import Reports from "./pages/Reports";
import Workbench from "./pages/Workbench";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="experiments/new" element={<Workbench />} />
        <Route path="experiments/:id" element={<ExperimentResults />} />
        <Route path="history" element={<History />} />
        <Route path="compare" element={<Compare />} />
        <Route path="cache-analysis" element={<CacheAnalysis />} />
        <Route path="reports" element={<Reports />} />
        <Route
          path="*"
          element={
            <EmptyState title="Page not found">
              <Link to="/" className="text-accent hover:underline">
                Back to the overview
              </Link>
            </EmptyState>
          }
        />
      </Route>
    </Routes>
  );
}
