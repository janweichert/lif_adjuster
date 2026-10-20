"""Brython glue for the LIF adjuster web UI.

Runs entirely in the browser: reads the uploaded LIF JSON, runs the shared
``lif_core.apply_transformations`` pipeline, streams the log to the page and
offers the adjusted JSON as a download. No data leaves the browser.
"""
from browser import document, html, window, ajax
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


progress_wrap = document["progress-wrap"]
progress_bar = document["progress-bar"]
progress_label = document["progress-label"]
process_btn = document["process-btn"]


def set_progress(done, total, label):
    pct = int(done * 100 / total) if total else 0
    progress_bar.style.width = str(pct) + "%"
    progress_label.text = "{} ({}/{})".format(label, done, total)


# Interpolate the bar within the current step for the heavy, chunked transforms.
def set_sub_progress(label, i, sub_total, done, total):
    step_frac = i / sub_total if sub_total else 1
    frac = (done - 1 + step_frac) / total if total else 0
    progress_bar.style.width = str(int(frac * 100)) + "%"
    progress_label.text = "{} - {}/{} ({}/{})".format(label, i, sub_total, done, total)


def show_progress():
    progress_wrap.removeAttribute("hidden")
    progress_bar.style.width = "0%"
    progress_label.text = ""
    process_btn.disabled = True


def finish_progress(done, total, aborted):
    process_btn.disabled = False
    if aborted:
        progress_label.text = "Aborted."
    else:
        progress_bar.style.width = "100%"
        progress_label.text = "Done ({}/{})".format(done, total)


def run(text, source_name):
    options = build_options()
    # Phases: parse (1) + each enabled transformation + serialize/download (1).
    total = lif_core.count_enabled_steps(options) + 2
    state = {"data": None, "done": 0, "label": "", "aborted": False}

    show_progress()

    # Yields a label before each phase runs (and ("sub", i, n) tuples within the
    # heavy steps) so the bar repaints between phases.
    def phases():
        yield "Parsing JSON"
        try:
            state["data"] = json.loads(text)
        except Exception as exc:
            logger.error("Could not parse JSON: %s", exc)
            state["aborted"] = True
            return

        for item in lif_core.iter_transformations(state["data"], options):
            if item is lif_core.ABORT:
                state["aborted"] = True
                return
            yield item

        yield "Serializing & downloading"
        out_text = json.dumps(state["data"], separators=(",", ":"), ensure_ascii=False)
        out_name = source_name.split(".")[0] + ".adjusted.json"
        trigger_download(out_text, out_name)
        logger.info("Done. Downloaded: %s", out_name)

    gen = phases()

    # Advance one phase per event-loop turn so the browser can repaint the bar.
    def pump(*_):
        try:
            item = next(gen)
        except StopIteration:
            finish_progress(state["done"], total, state["aborted"])
            return
        if isinstance(item, tuple):
            _, i, sub_total = item
            set_sub_progress(state["label"], i, sub_total, state["done"], total)
        else:
            state["done"] += 1
            state["label"] = item
            set_progress(state["done"], total, item)
        window.setTimeout(pump, 0)

    pump()


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


def on_file_change(evt):
    files = document["lif-file"].files
    document["file-name"].text = files[0].name if files.length else "No file selected"


# Option element ids, grouped by control type. Profile keys use these same ids.
BOOL_OPTION_IDS = [
    "fix_control_points_order",
    "replace_node_names_by_station_names",
    "write_node_name_to_description",
    "create_rack_offset",
    "remove_whitespace",
    "remove_map_id_prefix",
    "create_stations_from_park_nodes",
    "replace_ids_by_names",
]
TEXT_OPTION_IDS = ["remove_action_param", "remove_edge_prop"]
DEFAULT_PARK_THETA = "1.5707963267948966"

profiles_by_id = {}


# Reset every control to its default so a profile applies deterministically.
def reset_options():
    for oid in BOOL_OPTION_IDS:
        document[oid].checked = False
    for oid in TEXT_OPTION_IDS:
        document[oid].value = ""
    document["park_theta"].value = DEFAULT_PARK_THETA


# Apply a profile's option dict to the controls (unknown keys are ignored).
def apply_profile(options):
    reset_options()
    for oid in BOOL_OPTION_IDS:
        if oid in options:
            document[oid].checked = bool(options[oid])
    for oid in TEXT_OPTION_IDS:
        if oid in options:
            document[oid].value = str(options[oid])
    if "park_theta" in options:
        document["park_theta"].value = str(options["park_theta"])


def on_profile_change(evt):
    update_process_enabled()
    pid = document["profile-select"].value
    if pid in ("__custom__", "__none__"):
        return
    profile = profiles_by_id.get(pid)
    if not profile:
        return
    apply_profile(profile.get("options", {}))


# The Adjust & Download button and all option controls stay disabled until a
# real profile is chosen.
def update_process_enabled():
    disabled = document["profile-select"].value == "__none__"
    process_btn.disabled = disabled
    for oid in BOOL_OPTION_IDS + TEXT_OPTION_IDS + ["park_theta"]:
        document[oid].disabled = disabled


# A manual edit means the current state no longer matches a named profile.
def mark_custom(evt):
    document["profile-select"].value = "__custom__"
    update_process_enabled()


def on_profiles_loaded(req):
    if req.status not in (200, 0):
        logger.warning("Could not load profiles.json (status %s).", req.status)
        return
    try:
        data = json.loads(req.text)
    except Exception as exc:
        logger.warning("Could not parse profiles.json: %s", exc)
        return
    select = document["profile-select"]
    for profile in data.get("profiles", []):
        pid = profile.get("id")
        if not pid:
            continue
        profiles_by_id[pid] = profile
        select <= html.OPTION(profile.get("name", pid), value=pid)
    select <= html.OPTION("CUSTOM", value="__custom__")


def load_profiles():
    ajax.get("profiles.json", oncomplete=on_profiles_loaded)


document["profile-select"].bind("change", on_profile_change)
for _oid in BOOL_OPTION_IDS + TEXT_OPTION_IDS + ["park_theta"]:
    document[_oid].bind("change", mark_custom)
document["lif-file"].bind("change", on_file_change)
document["process-btn"].bind("click", on_process)
update_process_enabled()
load_profiles()
