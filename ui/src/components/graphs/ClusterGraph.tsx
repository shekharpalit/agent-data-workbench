import type { Cluster } from "../../contracts";
import { Bars, Card } from "../shared";

export default function ClusterGraph({
  clusters,
  onMembers,
}: {
  clusters: Cluster[];
  onMembers: (ids: string[]) => void;
}) {
  const total = clusters.reduce((count, group) => count + group.count, 0);
  const recurring = clusters.filter((group) => group.count > 1);
  const singletons = clusters
    .filter((group) => group.count === 1)
    .flatMap((group) => group.trace_ids);
  return (
    <Card
      title={
        recurring.length
          ? "How often does each pattern occur?"
          : "No recurring groups at this threshold"
      }
    >
      <p>
        {recurring.length
          ? "Bar length counts traces in each recurring lexical group. Click a bar label to inspect every member. Shared language suggests a place to investigate; it does not establish the same failure."
          : "These traces have no close lexical neighbors at the selected threshold. Try a lower threshold or a more focused content field, then inspect the evidence."}
      </p>
      <Bars
        values={recurring.map((group, index) => ({
          value: `${index + 1}. ${group.label || "Unlabelled group"}`,
          count: group.count,
        }))}
        total={total}
        onSelect={(value) => {
          const selected = recurring.find(
            (group, i) =>
              `${i + 1}. ${group.label || "Unlabelled group"}` === value,
          );
          if (selected) onMembers(selected.trace_ids);
        }}
      />
      <p>{singletons.length} traces have no neighbor at this threshold.</p>
      {!!singletons.length && (
        <button className="secondary" onClick={() => onMembers(singletons)}>
          Inspect ungrouped traces →
        </button>
      )}
      <small>
        {total} traces across {clusters.length} lexical components · counts, not
        semantic distance
      </small>
    </Card>
  );
}
