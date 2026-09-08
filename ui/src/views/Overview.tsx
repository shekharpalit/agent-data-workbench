import type { Overview, Route } from "../contracts";
import { Badge, Bars, Card } from "../components/shared";

export function OverviewView({
  data,
  navigate,
  onGroup,
}: {
  data: Overview;
  navigate: (route: Route) => void;
  onGroup: (group: string) => void;
}) {
  return (
    <>
      <Card className="hero">
        <span className="kicker">FROM AGENT EXPERIENCE TO EVIDENCE</span>
        <h2>{data.project.objective}</h2>
        <p>
          Investigate what happened, review what good looks like, and measure
          the next change.
        </p>
        <div className="row hero-actions">
          <button onClick={() => navigate({ view: "traces" })}>
            Explore the data →
          </button>
          <button
            className="secondary"
            onClick={() => navigate({ view: "investigations" })}
          >
            Start an investigation
          </button>
        </div>
      </Card>
      <div className="grid metrics">
        {[
          {
            title: "Traces indexed",
            value: data.inventory.total,
            description: "Raw evidence, preserved locally",
          },
          {
            title: "Reviewed tasks",
            value: data.task_counts.accepted,
            description: "Accepted after a grader audit",
          },
          {
            title: "Experiments recorded",
            value: data.experiments.length,
            description: "Baseline and candidate, side by side",
          },
        ].map((item) => (
          <Card key={item.title} title={item.title}>
            <div className="metric">{item.value}</div>
            <small>{item.description}</small>
          </Card>
        ))}
      </div>
      <div className="grid two chart-card">
        <Card title="Trace coverage">
          <Bars
            values={Object.entries(data.inventory.strata).map(
              ([value, count]) => ({ value, count }),
            )}
            total={data.inventory.total}
            onSelect={(value) => onGroup(String(value))}
          />
          <small>Corpus counts. Select a group to inspect its traces.</small>
        </Card>
        <Card title="Review queue">
          <Bars
            values={Object.entries(data.task_counts).map(([value, count]) => ({
              value,
              count,
            }))}
            total={Object.values(data.task_counts).reduce((a, b) => a + b, 0)}
          />
          <button className="ghost" onClick={() => navigate({ view: "tasks" })}>
            Review tasks →
          </button>
        </Card>
      </div>
      <Card title="Recent experiments">
        {[...data.experiments]
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
          .slice(0, 3)
          .map((experiment) => (
            <div className="item" key={experiment.id}>
              <div className="item-head">
                <h3>{experiment.conclusion}</h3>
                <Badge value={experiment.split} />
              </div>
              <button
                className="ghost"
                onClick={() =>
                  navigate({ view: "experiments", id: experiment.id })
                }
              >
                {experiment.id}
              </button>
            </div>
          ))}
        {!data.experiments.length && (
          <p className="muted">
            Run a Harbor comparison from an accepted task or a reviewed suite
            from Improvements. Results will appear here.
          </p>
        )}
      </Card>
    </>
  );
}
