"""Brython glue for the LIF adjuster web UI.

Runs entirely in the browser: reads the uploaded LIF JSON, runs the shared
``lif_core.apply_transformations`` pipeline, streams the log to the page and
offers the adjusted JSON as a download. No data leaves the browser.
"""
from browser import document, html, window
import json
import logging

import lif_core


log_area = document["log"]


# Route the shared core's logging output into the on-page log panel.
class DomLogHandler(logging.Handler):
    def emit(self, record):
        line = html.DIV(self.format(record))
        line.classList.add("log-" + record.levelname.lower())
        log_area <= line


logger = logging.getLogger("LIFadjuster")
logger.setLevel(logging.INFO)
logger.addHandler(DomLogHandler())

# Show the shared version in the title bar and page heading.
document["app-version"].text = "v" + lif_core.__version__
document.title = "StackDesigner LIF Export Adjuster v" + lif_core.__version__


# A plain attribute bag matching the argparse Namespace the core expects.
class Options:
    pass


# Split a free-text field into a list of keys (comma or whitespace separated).
def parse_keys(raw):
    if not raw:
        return []
    return [k.strip() for k in raw.replace(",", " ").split() if k.strip()]


def build_options():
    opts = Options()
    opts.fix_control_points_order = document["fix_control_points_order"].checked
    opts.replace_node_names_by_station_names = document["replace_node_names_by_station_names"].checked
    opts.write_node_name_to_description = document["write_node_name_to_description"].checked
    opts.create_rack_offset = document["create_rack_offset"].checked
    opts.remove_whitespace = document["remove_whitespace"].checked
    opts.remove_map_id_prefix = document["remove_map_id_prefix"].checked
    opts.create_stations_from_park_nodes = document["create_stations_from_park_nodes"].checked
    opts.replace_ids_by_names = document["replace_ids_by_names"].checked
    opts.remove_action_param = parse_keys(document["remove_action_param"].value)
    opts.remove_edge_prop = parse_keys(document["remove_edge_prop"].value)

    try:
        opts.park_theta = float(document["park_theta"].value)
    except (ValueError, TypeError):
        opts.park_theta = 1.5707963267948966

    return opts


def trigger_download(text, filename):
    blob = window.Blob.new([text], {"type": "application/json"})
    url = window.URL.createObjectURL(blob)
    link = html.A(href=url, download=filename)
    link.style.display = "none"
    document <= link
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)


def run(text, source_name):
    logger.setLevel(logging.DEBUG if document["verbose"].checked else logging.INFO)

    try:
        data = json.loads(text)
    except Exception as exc:
        logger.error("Could not parse JSON: %s", exc)
        return

    try:
        applied = lif_core.apply_transformations(data, build_options())
    except Exception as exc:
        logger.error("Processing failed: %s", exc)
        return

    if not applied:
        return

    out_text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    out_name = source_name.split(".")[0] + ".adjusted.json"
    trigger_download(out_text, out_name)
    logger.info("Done. Downloaded: %s", out_name)


def on_process(evt):
    files = document["lif-file"].files
    if not files.length:
        logger.error("Please choose a LIF .json file first.")
        return

    log_area.clear()
    file = files[0]
    reader = window.FileReader.new()

    def on_loaded(e):
        run(reader.result, file.name)

    reader.onload = on_loaded
    reader.readAsText(file)


document["process-btn"].bind("click", on_process)
