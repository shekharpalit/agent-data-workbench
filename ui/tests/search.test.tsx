import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchForm } from "../src/views/Search";
import { initialSearch } from "../src/state";

describe("advanced search form", () => {
  it("Given JSON strings that resemble other types, When applying unchanged filters, Then preserves their types", async () => {
    // Given
    const user = userEvent.setup();
    const onApply = vi.fn();
    const query = {
      ...initialSearch,
      filters: ['"1"', '"true"', '"null"', '""'].map((value_json) => ({
        pointer: "/value",
        operator: "equals" as const,
        value_json,
      })),
    };
    render(<SearchForm query={query} onApply={onApply} />);
    // When
    await user.click(screen.getByRole("button", { name: /^Search$/ }));
    // Then
    expect(onApply.mock.calls).toStrictEqual([[query]]);
  });
  it("Given trace filters, When combining status and latency, Then submits a typed AND query", async () => {
    // Given
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<SearchForm query={initialSearch} onApply={onApply} />);
    // When
    await user.type(screen.getByLabelText("Search trace content"), "refund");
    await user.type(screen.getByLabelText("Agent group"), "support");
    await user.click(
      screen.getByRole("button", { name: "+ Add field filter" }),
    );
    await user.click(
      screen.getByRole("button", { name: "+ Add field filter" }),
    );
    await user.clear(screen.getByLabelText("Field 2"));
    await user.type(screen.getByLabelText("Field 2"), "/latency_ms");
    await user.selectOptions(screen.getByLabelText("Condition 2"), "gte");
    await user.clear(screen.getByLabelText("Value 2"));
    await user.type(screen.getByLabelText("Value 2"), "500");
    await user.selectOptions(screen.getByLabelText("Direction"), "desc");
    await user.click(screen.getByRole("button", { name: /^Search$/ }));
    // Then
    expect(onApply.mock.calls).toStrictEqual([
      [
        {
          text: "refund",
          stratum: "support",
          filters: [
            {
              pointer: "/tool_result/status",
              operator: "equals",
              value_json: '"declined"',
            },
            { pointer: "/latency_ms", operator: "gte", value_json: "500" },
          ],
          sort: "trace_id",
          direction: "desc",
          limit: 20,
          offset: 0,
          trace_ids: null,
        },
      ],
    ]);
  });
  it("Given an invalid numeric filter, When searching, Then preserves input and explains the error", async () => {
    // Given
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(
      <SearchForm
        query={{
          ...initialSearch,
          filters: [
            { pointer: "/latency_ms", operator: "gte", value_json: "500" },
          ],
        }}
        onApply={onApply}
      />,
    );
    // When
    await user.clear(screen.getByLabelText("Value 1"));
    await user.type(screen.getByLabelText("Value 1"), "not a number");
    await user.click(screen.getByRole("button", { name: /^Search$/ }));
    // Then
    expect({
      calls: onApply.mock.calls,
      error: screen.getByRole("alert").textContent,
      input: (screen.getByLabelText("Value 1") as HTMLInputElement).value,
    }).toStrictEqual({
      calls: [],
      error: "Numeric ranges require a number.",
      input: "not a number",
    });
  });
  it("Given a cluster-filtered page, When resetting, Then returns to the whole corpus", async () => {
    // Given
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(
      <SearchForm
        query={{
          ...initialSearch,
          text: "refund",
          offset: 20,
          trace_ids: ["r1"],
        }}
        onApply={onApply}
      />,
    );
    // When
    await user.click(screen.getByRole("button", { name: "Reset" }));
    // Then
    expect(onApply.mock.calls).toStrictEqual([
      [
        {
          text: "",
          stratum: "",
          filters: [],
          sort: "trace_id",
          direction: "asc",
          limit: 20,
          offset: 0,
          trace_ids: null,
        },
      ],
    ]);
  });
});
