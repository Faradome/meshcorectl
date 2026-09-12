# Example scripts

Ported from the original [meshcore-cli](https://github.com/meshcore-dev/meshcore-cli)'s
`scripts/` directory (see [docs/migration-from-meshcli.md](../../docs/migration-from-meshcli.md)
for the full picture). None of these depend on meshcorectl's interactive features — the
originals used them only to feed data *into* the old tool's line-redirection DSL, which
meshcorectl doesn't have (a plain shell already does that job, see PLAN.md §6).

- **`contact_markers.sh`** — draws a map with a marker per contact, using
  [coords2img](https://github.com/fdlamotte/coords2img). Rewritten for meshcorectl: two
  `meshcorectl ... -o json` calls piped through `jq`, replacing the original's
  input-redirection into `jc`.
- **`getpos.py`** — queries device position via GeoClue2 (Linux). Unchanged from the original;
  only how you feed its output to meshcorectl changed (see the file's own header comment).
- **`ask_mepo_coords`** — a `mepo` map-based coordinate picker (Linux phones). Also unchanged;
  same consumption-pattern note as `getpos.py`.

**Not ported:** `neighbour_map.sh`, which drew a map of a repeater's neighbours from
`request_neighbours`/`req_neighbours`. That underlying request isn't implemented in meshcorectl
yet (see the migration guide's "Not yet in meshcorectl" table) — the library that talks to the
device already exposes it, so it's a well-scoped future addition following the same
`mesh_data.py` helper + command + tests pattern every other command here uses, not a redesign.
