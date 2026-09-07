import { describe, expect, it, vi } from "vitest";
import { ApiClient, sessionToken } from "../src/api";
import { initialSearch } from "../src/state";

describe("local API client", () => {
  it("Given the browser fetch function, When using default transport, Then does not rebind it to the client", async () => {
    // Given
    const receivers: unknown[] = [];
    vi.stubGlobal("fetch", async function (this: unknown) {
      receivers.push(this);
      if (this !== undefined && this !== globalThis)
        throw new TypeError("Illegal invocation");
      return new Response(JSON.stringify([]));
    });
    const client = new ApiClient(() => "test");
    try {
      // When
      const actual = await client.jobs();
      // Then
      expect({
        result: actual,
        clientReceiver: receivers.includes(client),
      }).toStrictEqual({ result: [], clientReceiver: false });
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("Given a typed query, When searching, Then sends the full query and bearer header", async () => {
    // Given
    const result = { ids: ["r1"], eligible: 1, selected: 1 };
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify(result)));
    const client = new ApiClient(() => "local-test-token", transport);
    // When
    const actual = await client.search(initialSearch);
    // Then
    expect({ response: actual, calls: transport.mock.calls }).toStrictEqual({
      response: { ids: ["r1"], eligible: 1, selected: 1 },
      calls: [
        [
          "/api/search",
          {
            method: "POST",
            headers: {
              Authorization: "Bearer local-test-token",
              "Content-Type": "application/json",
            },
            body: '{"text":"","stratum":"","filters":[],"sort":"trace_id","direction":"asc","limit":20,"offset":0,"trace_ids":null}',
          },
        ],
      ],
    });
  });
  it("Given an expired session, When reading data, Then exposes the server error", async () => {
    // Given
    const transport = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ error: "Open the complete local URL" }), {
        status: 401,
      }),
    );
    const client = new ApiClient(() => "", transport);
    // When
    const actual = await client.overview().then(
      () => ({ message: "unexpected success" }),
      (error: Error) => ({ message: error.message }),
    );
    // Then
    expect(actual).toStrictEqual({ message: "Open the complete local URL" });
  });
  it("Given an aborted search, When requesting data, Then forwards cancellation", async () => {
    // Given
    const controller = new AbortController();
    const transport = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new DOMException("Aborted", "AbortError"));
    const client = new ApiClient(() => "test", transport);
    // When
    controller.abort();
    const actual = await client
      .search(initialSearch, controller.signal)
      .catch((error: Error) => ({ name: error.name }));
    // Then
    expect({
      result: actual,
      signal: transport.mock.calls[0]?.[1]?.signal,
    }).toStrictEqual({
      result: { name: "AbortError" },
      signal: controller.signal,
    });
  });
  it("Given a new URL token, When initializing, Then replaces an old session", () => {
    // Given
    const hash = "#token=fresh-local-session";
    // When
    const actual = {
      replaced: sessionToken(hash, "old"),
      retained: sessionToken("", "old"),
    };
    // Then
    expect(actual).toStrictEqual({
      replaced: "fresh-local-session",
      retained: "old",
    });
  });
});
