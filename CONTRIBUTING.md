# Contributing

Keep the core independent of any agent framework. Trace import, analysis, artifact generation, and evaluation are separate modules.

Start with `uv sync`, then run `uv run pytest -q` and `uv run ruff check src tests`.

The UI is React + TypeScript. Use `npm ci --prefix ui`, `npm --prefix ui run build` and `npm --prefix ui test`. Run `npm --prefix ui run format:check` before handing off changes. Commit the resulting `src/agent_data_workbench/web` assets along with source changes so Python installations work without Node. Do not commit `node_modules`. See [ui/README.md](ui/README.md).

## Test conventions

Use **Given / When / Then** sections: arrange inputs, perform the operation, and compare the expected result. Keep the operation out of the assertion when practical. Exception tests can combine `When / Then` with `pytest.raises`. Name tests after observable behavior; prefer several focused cases to a long sequence of unrelated actions.

Compare structured results as whole objects. In TypeScript use `expect(actual).toStrictEqual(expected)`; `{} === {}` tests identity and is not a deep comparison. In Python use `assert actual == expected`. For volatile IDs or timestamps, compare an explicit meaningful projection while testing provenance separately. Avoid snapshots that simply copy current implementation output.

```ts
// Given
const state = { ...initialSearch, offset: 40 };
// When
const actual = searchReducer(state, { type: "cluster", ids: ["run-1"] });
// Then
expect(actual).toStrictEqual({ ...initialSearch, trace_ids: ["run-1"] });
```

```python
# Given
query = SearchQuery(trace_ids=["run-1"], limit=10)
# When
page = search(store, query)
# Then
assert {"ids": page["ids"], "eligible": page["eligible"]} == {
    "ids": ["run-1"], "eligible": 1,
}
```

API changes belong in `src/agent_data_workbench/api.py` and its Pydantic request models. Use FastAPI routes and `StaticFiles`; keep domain logic in the SDK. Add Given–When–Then API tests with FastAPI TestClient and preserve the TypeScript client contract. The existing HTTP tests also cover the actual Uvicorn launcher.

Database changes belong in `database.py` and `store.py`. Use SQLAlchemy 2 mapped models, sessions and query expressions; do not add raw SQL strings or direct `sqlite3` access. Preserve existing SQLite files, canonical JSON and batch rollback behavior. Consumers such as `explore.py` should use `TraceStore` rather than reaching into the database. Never share a session between API worker threads.

Changes to the analysis contract need compatible provider schemas and tests that exercise meaningful behavior: incorrect evidence, missing context, malformed output, review decisions, or regressions. Use synthetic fixtures in tests and clearly label precomputed results. Tests must not require provider credentials or network access.

Keep output formats portable. Add a source or analyzer adapter without assuming all users adopt its framework. Never report a generated candidate as an executed or validated environment.

Do not include private production traces or account credentials in contributions.
