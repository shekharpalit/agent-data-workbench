import { lazy, Suspense, useReducer, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Route, SearchQuery, View } from "./contracts";
import { initialSearch, searchReducer } from "./state";
import { ResourceState } from "./components/shared";
import { OverviewView } from "./views/Overview";
import { SearchView, TraceDetail } from "./views/Search";
import { ClustersView } from "./views/Clusters";
import {
  InvestigationsView,
  InvestigationDetail,
} from "./views/Investigations";
import { KnowledgeView } from "./views/Knowledge";
import { TasksView, TaskDetail } from "./views/Tasks";
import { ExperimentsView, ExperimentDetail } from "./views/Experiments";

import { WorldsView } from "./views/Worlds";
import { CalibrationView } from "./views/Calibration";
import { BehavioralCoverageView } from "./views/BehavioralCoverage";
import { ImprovementsView } from "./views/Improvements";

const GraphView = lazy(() => import("./views/Graph"));
const labels: Record<View, string> = {
  overview: "Overview",
  traces: "Trace explorer",
  clusters: "Clusters",
  graph: "Evidence graph",
  investigations: "Investigations",
  knowledge: "Project knowledge",
  tasks: "Tasks & graders",
  experiments: "Experiments",
  worlds: "World specifications",
  calibration: "Grader calibration",
  coverage: "Behavioral coverage",
  improvements: "Improvements",
};
const navigation: View[] = [
  "overview",
  "traces",
  "clusters",
  "graph",
  "investigations",
  "knowledge",
  "tasks",
  "experiments",
  "worlds",
  "calibration",
  "coverage",
  "improvements",
];

export default function App() {
  const [route, setRoute] = useState<Route>({ view: "overview" });
  const [query, dispatch] = useReducer(searchReducer, initialSearch);
  const client = useQueryClient();
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: ({ signal }) => api.overview(signal),
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: ({ signal }) => api.jobs(signal),
    refetchInterval: (state) =>
      state.state.data?.some((job) => job.status === "running") ? 2000 : false,
  });
  function navigate(next: Route) {
    setRoute(next);
    window.scrollTo(0, 0);
  }
  function setQuery(next: SearchQuery) {
    dispatch({ type: "apply", query: next });
  }
  // Pagination is the only query update that retains a nonzero offset.
  function searchChange(next: SearchQuery) {
    const { offset: previousOffset, ...previous } = query;
    const { offset, ...updated } = next;
    if (
      JSON.stringify(previous) === JSON.stringify(updated) &&
      offset !== previousOffset
    )
      dispatch({ type: "page", offset });
    else setQuery(next);
  }
  function page() {
    switch (route.view) {
      case "overview":
        return overview.data ? (
          <OverviewView
            data={overview.data}
            navigate={navigate}
            onGroup={(stratum) => {
              setQuery({ ...initialSearch, stratum });
              navigate({ view: "traces" });
            }}
          />
        ) : (
          <ResourceState error={overview.error} />
        );
      case "traces":
        return route.id ? (
          <TraceDetail id={route.id} navigate={navigate} />
        ) : (
          <SearchView
            query={query}
            onQuery={searchChange}
            navigate={navigate}
          />
        );
      case "clusters":
        return (
          <ClustersView
            key={JSON.stringify(query)}
            query={query}
            onMembers={(ids) => {
              dispatch({ type: "cluster", ids });
              navigate({ view: "traces" });
            }}
          />
        );
      case "graph":
        return (
          <Suspense fallback={<ResourceState />}>
            <GraphView
              key={route.id || "all"}
              traceId={route.id}
              navigate={navigate}
            />
          </Suspense>
        );
      case "investigations":
        return route.id ? (
          <InvestigationDetail id={route.id} navigate={navigate} />
        ) : (
          <InvestigationsView navigate={navigate} />
        );
      case "knowledge":
        return <KnowledgeView />;
      case "tasks":
        return route.id ? (
          <TaskDetail id={route.id} navigate={navigate} />
        ) : (
          <TasksView navigate={navigate} />
        );
      case "worlds":
        return <WorldsView />;
      case "calibration":
        return <CalibrationView navigate={navigate} />;
      case "coverage":
        return <BehavioralCoverageView navigate={navigate} />;
      case "improvements":
        return <ImprovementsView navigate={navigate} />;
      case "experiments":
        return route.id ? (
          <ExperimentDetail key={route.id} id={route.id} navigate={navigate} />
        ) : (
          <ExperimentsView navigate={navigate} />
        );
    }
  }
  return (
    <>
      <aside>
        <button
          className="brand"
          onClick={() => navigate({ view: "overview" })}
        >
          <span className="mark">dw</span>
          <span className="brand-label">Agent Data Workbench</span>
        </button>
        <p className="eyebrow">LOCAL WORKBENCH</p>
        <nav aria-label="Workbench">
          {navigation.map((view) => (
            <button
              key={view}
              className={view === route.view ? "active" : ""}
              aria-current={view === route.view ? "page" : undefined}
              onClick={() => navigate({ view })}
            >
              {labels[view]}
            </button>
          ))}
        </nav>
        <div className="aside-bottom">
          <span className="dot" />
          Local artifacts
          <br />
          <small>Research. Review. Improve.</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">
              {overview.data?.project.name || "YOUR AGENT, UNDERSTOOD"}
            </p>
            <h1>
              {route.view === "overview"
                ? "Make the next version better."
                : labels[route.view]}
            </h1>
          </div>
          <button
            className="secondary"
            onClick={() => void client.invalidateQueries()}
          >
            Refresh data ↻
          </button>
        </header>
        {!!jobs.data?.length && (
          <div className="jobs" role="status">
            {jobs.data.slice(-2).map((job) => (
              <p key={job.id}>
                {job.name} · {job.status}
                {job.error ? ` · ${job.error}` : ""}
              </p>
            ))}
            <button
              className="ghost"
              onClick={() => void client.invalidateQueries()}
            >
              Refresh results
            </button>
          </div>
        )}
        <section aria-label="Workbench content">{page()}</section>
      </main>
    </>
  );
}
