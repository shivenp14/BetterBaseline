# Backend resource and cache behavior

## Grid resource guards

The grid endpoint checks its public axis and enrollment ceilings and the
application's configured `max_grid_cells` and `max_enrolled_per_arm` before it
looks in the cache or starts numerical work. These checks also run for cache
hits. A request rejected by a configured resource limit returns the standard
validation error envelope. When an app's shared compute permits are all in use,
uncached work returns a retryable `429` response with `Retry-After`; the permit
is released if computation succeeds or raises an error.

Each `create_app` instance owns its own compute guard, bounded LRU cache, and
compute permits. Cached results and concurrency capacity are not shared between
app instances.

## Grid cache and timestamps

Grid cache keys are deterministic and include the route, the full normalized
request (including axes, target, effect, enrollment, selected scenario, and
provenance), model and analytical method versions, and the Python/NumPy/SciPy/
statsmodels runtime versions. Repeating an identical request under the same
versions returns the original cached response. Its `computed_at` is the time of
the original calculation and remains unchanged on a cache hit. An export's
`exported_at` records when that export was created and is separate from the
grid's `computed_at`.

Changing any request input or runtime version produces a different cache key.
When a model or analytical method changes in a way that can change results,
bump the model or `GRID_METHOD_VERSION` value so older entries cannot be reused.
The cache is process-local and bounded; restarting the process clears it.
