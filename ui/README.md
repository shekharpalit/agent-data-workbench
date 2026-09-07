# TypeScript workbench

React + TypeScript, TanStack Query, Vite, React Flow and Vitest. Requires Node 22.12+ and npm for development. Python users receive compiled assets and do not need Node.

From the repository root:

```sh
npm ci --prefix ui
npm --prefix ui run build
uv run agent-data-workbench ui runs/workbench --open-browser
```

For development, run `npm --prefix ui run dev` in a second terminal. This watches and rebuilds the packaged assets; reload the workbench after a build. FastAPI and Uvicorn serve the app and authenticated API on the same origin, with no CORS or development proxy configuration.

```sh
npm --prefix ui run typecheck
npm --prefix ui test
npm --prefix ui run format
npm --prefix ui run format:check
```

`src/contracts.ts` defines the JSON boundary, `api.ts` handles transport, `state.ts` owns pure query transitions and graph layout, and `views/` contains feature components. `components/shared.tsx` contains shared presentation and explicit mutation controls. The graph is a separate lazy-loaded bundle. API responses are typed at the client boundary; backend Pydantic models validate requests and integration tests check the wire contract.

New tests use Given / When / Then and `toStrictEqual` for complete object comparisons. Component tests exercise filter entry, invalid input and query submission. Python tests cover search semantics, cluster bounds and graph provenance. Provider calls remain explicit user actions; exploring data never calls a model.

`npm run build` replaces `../src/agent_data_workbench/web`. Keep these generated assets with source changes; never edit the generated JavaScript directly. `ui/index.html` only mounts the TypeScript app. Markdown reports remain independent CLI/CI exports.

Search currently scans local SQLite; it is not an indexed search engine. Clusters use a bounded TF-IDF selection, not embeddings. See [architecture](../docs/ARCHITECTURE.md) for current limits and extension points.

The backend exposes the same UI routes through explicit FastAPI handlers. Request schemas are available to authenticated clients at `/api/openapi.json`; the frontend uses its existing typed client. The backend maps validation failures into the existing HTTP 400 `{"error": "…"}` contract.
