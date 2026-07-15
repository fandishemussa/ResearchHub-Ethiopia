# ResearchHub Ethiopia frontend

The semantic-search interface is available at `/search/semantic`. It calls
`GET /api/search/semantic` through the shared typed API client.

## Local development

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

`NEXT_PUBLIC_API_URL` must be reachable by the browser. The local example uses
`http://localhost:8111/api`. When it is omitted, browser requests use the
same-origin `/backend-api` proxy, whose server-side destination is configured
with `INTERNAL_API_URL` (for example, `http://api:8111` in Compose). Never use a
Docker service hostname in `NEXT_PUBLIC_API_URL`; browsers cannot resolve it.
Searches and functional filters (`source`, `limit`,
and `minSimilarity`) are synchronized to the URL, so a result view can be
bookmarked or shared. Unsupported future filters are displayed as coming later
and are never sent to the API.

Example searches include maternal health challenges, crop disease detection,
groundwater modelling, drought-resistant sorghum, and inclusive education.

## Checks

```powershell
npm run lint
npm run type-check
npm test
npm run build
```

Tests mock `fetch`; they do not require the backend, Docker, model weights, or
internet access.

## Troubleshooting

- Confirm API health with `Invoke-RestMethod http://localhost:8111/health`.
- A network error usually means `NEXT_PUBLIC_API_URL` is not browser-reachable.
- A missing endpoint means the backend semantic-search route is not deployed.
- Empty results can mean no close matches, a restrictive threshold, or that
  publication embeddings have not been generated.
- Restart `npm run dev` after changing public environment variables.
