# StackDesigner LIF Export Adjuster

A browser-based tool that adjusts StackDesigner LIF export JSON files via a
configurable transformation pipeline. You upload a `.json`, pick the
adjustments, and download the `*.adjusted.json` result. Everything runs
client-side (Python via [Brython](https://brython.info/)) — no file is ever
uploaded to a server.

Before transforming, it always checks that all nodes/edges have `vehicleType`
properties; if any are missing it reports them and aborts.

## Run locally

The page must be served over HTTP (browsers block Brython from loading local
files via `file://`). Double-click `run_webpage.bat`, or run:

```bat
py -m http.server 8777 --directory docs
```

Then open <http://localhost:8777/>.

## Adjustments

| Option | Effect |
| --- | --- |
| Fix order of trajectory control points | Reverse trajectory control points when start/end are swapped. |
| Rename interaction nodes/edges to station name | Rename interaction nodes/edges to the station name. |
| Copy node name into node description | Copy `nodeName` into `nodeDescription`. |
| Offset stacked rack station nodes | Offset stacked rack station nodes by `stationHeight`. |
| Remove whitespace from node/edge/station names | Strip whitespace from names. |
| Remove "0.0." prefix from node mapId | Remove the `0.0.` prefix from node `mapId`. |
| Create stations from "park" nodes | Create stations from nodes whose name contains `park`. |
| Replace node/edge/station ids with names | Replace ids (and their references) with names. |
| Remove action parameter keys | Remove actionParameter key(s) from node actions. |
| Remove vehicleTypeEdgeProperties keys | Remove key(s) from `vehicleTypeEdgeProperties`. |
| Park station theta | Theta for stations created from park nodes (default `1.5707963267948966`). |
| Verbose (debug) logging | Enable verbose logging in the on-page log panel. |

## Project layout

| Path | Role |
| --- | --- |
| `docs/index.html` | Web UI. |
| `docs/app.py` | Brython glue: upload → process → download, logs to the page. |
| `docs/lif_core.py` | Pure transformation pipeline and version (single source of truth). |
| `run_webpage.bat` | Serve `docs/` locally and open the browser. |
| `.github/workflows/deploy-pages.yml` | Deploy `docs/` to GitHub Pages on each `v*` tag. |

## Deploy

GitHub Pages is published from `docs/` via GitHub Actions. In the repo settings,
set **Pages → Build and deployment → Source = GitHub Actions**. Pushing a tag
such as `v1.0.2` (which must match `__version__` in `docs/lif_core.py`) deploys
the site to `https://<you>.github.io/<repo>/`.
