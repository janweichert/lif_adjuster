"""Pure LIF transformation logic for the web (Brython) UI.

This module must stay free of file-system / OS access (no `open`, no `os`) so it
can run unchanged inside the browser via Brython. File I/O (reading the uploaded
file and triggering the download) lives in ``app.py``.
"""
import logging
from collections import defaultdict

__version__ = "1.1.0"

logger = logging.getLogger("LIFadjuster")


# Return the word in singular or plural form based on count.
def plural(count, singular, plural_form=None):
    if count == 1:
        return singular
    return plural_form if plural_form is not None else singular + "s"


# Nudge stacked rack stations apart by offsetting their interaction node x-position.
# Generator: yields (processed, total) every `chunk` stations and appends the final
# edited count to `out`, so the web UI can show sub-progress for this heavy step.
def createRackOffset_steps(lif, out, chunk=50):
    stations_by_coordinates = defaultdict(list)

    for station in lif["layouts"][0]["stations"]:
        x = station["stationPosition"]["x"]
        y = station["stationPosition"]["y"]
        key = (x, y)
        stations_by_coordinates[key].append(station)

    # Sort each group by stationHeight
    for key in stations_by_coordinates.keys():
        stations_by_coordinates[key].sort(key=lambda s: s["stationHeight"])

        # Remove the first element if the group has at least one station
        if stations_by_coordinates[key]:
            stations_by_coordinates[key].pop(0)

    # Convert the dictionary into a list of grouped stations
    grouped_stations = list(stations_by_coordinates.values())
    nodes = lif["layouts"][0]["nodes"]
    total = sum(len(group) for group in grouped_stations)

    edited = 0
    processed = 0
    for group in grouped_stations:
        counter = 0
        for station in group:
            counter += 1
            processed += 1
            for node in nodes:
                if node["nodeId"] == station["interactionNodeIds"][0]:
                    node["nodePosition"]["x"] = round(node["nodePosition"]["x"] + 0.001 * counter, 3)
                    edited += 1
            if processed % chunk == 0 or processed == total:
                yield processed, total
    out.append(edited)


def createRackOffset(lif):
    out = []
    for _ in createRackOffset_steps(lif, out):
        pass
    return out[0] if out else 0


# Remove a given actionParameter key from all node actions.
def removeNodeActionParameter(lif, param_key):
    removed = 0
    for node in lif["layouts"][0]["nodes"]:
        vt_props = node.get("vehicleTypeNodeProperties")

        if isinstance(vt_props, list):
            for vt in vt_props:
                actions = vt.get("actions", [])

                for action in actions:
                    params = action.get("actionParameters", [])
                    filtered = [p for p in params if p.get("key") != param_key]
                    removed += len(params) - len(filtered)
                    action["actionParameters"] = filtered
    return removed


# Remove a given property key from every vehicleTypeEdgeProperties entry.
def removeVehicleTypeEdgeProperties(lif, property_key):
    removed = 0
    for edge in lif["layouts"][0]["edges"]:
        vt_props = edge.get("vehicleTypeEdgeProperties")

        if isinstance(vt_props, list):
            for vt in vt_props:
                if isinstance(vt, dict) and property_key in vt:
                    vt.pop(property_key, None)
                    removed += 1
    return removed


# Replace each stationId with its stationName.
def replaceStationIdsByNames(lif):
    stations = lif["layouts"][0]["stations"]
    for station in stations:
        station["stationId"] = station["stationName"]
    return len(stations)


# Reverse edge control points when they run opposite to the start/end node direction.
def fixOrderOfControlPoints(lif):
    tolerance = 1e-6  # use tight tolerance for floating point comparison
    reversed_count = 0

    nodes_by_id = {}
    for node in lif["layouts"][0]["nodes"]:
        nodes_by_id.setdefault(node["nodeId"], node)

    for edge in lif["layouts"][0]["edges"]:
        startNode = nodes_by_id.get(edge["startNodeId"])
        if startNode is None:
            logger.warning("Node not found: %s", edge["startNodeId"])
        endNode = nodes_by_id.get(edge["endNodeId"])
        if endNode is None:
            logger.warning("Node not found: %s", edge["endNodeId"])

        if not edge.get("vehicleTypeEdgeProperties"):
            continue

        controlStartX = edge["vehicleTypeEdgeProperties"][0]["trajectory"]["controlPoints"][0]["x"]
        controlStartY = edge["vehicleTypeEdgeProperties"][0]["trajectory"]["controlPoints"][0]["y"]
        controlEndX = edge["vehicleTypeEdgeProperties"][0]["trajectory"]["controlPoints"][-1]["x"]
        controlEndY = edge["vehicleTypeEdgeProperties"][0]["trajectory"]["controlPoints"][-1]["y"]

        controlPoints = edge["vehicleTypeEdgeProperties"][0]["trajectory"]["controlPoints"]

        # Use approximate floating-point comparison instead of strict equality
        start_matches = (abs(startNode["nodePosition"]["x"] - controlStartX) < tolerance and
                        abs(startNode["nodePosition"]["y"] - controlStartY) < tolerance)
        end_matches = (abs(endNode["nodePosition"]["x"] - controlEndX) < tolerance and
                      abs(endNode["nodePosition"]["y"] - controlEndY) < tolerance)

        if not (start_matches and end_matches):
            controlPoints = controlPoints[::-1]
            reversed_count += 1

        edge["vehicleTypeEdgeProperties"][0]["trajectory"]["controlPoints"] = controlPoints
    return reversed_count


# Rename interaction nodes (and their edge names) after the station they belong to.
# Single pass over nodes and edges using an interactionNodeId -> stationName map
# (last station wins). Generator: yields (processed, total) every `chunk` items and
# appends the final renamed count to `out`, so the web UI can show sub-progress.
def replaceNodeNamesByStationNames_steps(lif, out, chunk=500):
    stations = lif["layouts"][0]["stations"]
    nodes = lif["layouts"][0]["nodes"]
    edges = lif["layouts"][0]["edges"]

    id_to_name = {}
    for station in stations:
        interaction_ids = station.get("interactionNodeIds") or []
        if interaction_ids:
            id_to_name[interaction_ids[0]] = station["stationName"]

    total = len(nodes) + len(edges)
    processed = 0
    renamed = 0

    for node in nodes:
        name = id_to_name.get(node["nodeId"])
        if name is not None:
            node["nodeName"] = name
            renamed += 1
        processed += 1
        if processed % chunk == 0 or processed == total:
            yield processed, total

    for edge in edges:
        startNodeName, endNodeName = edge["edgeName"].split(" => ", 1)
        start_name = id_to_name.get(edge.get("startNodeId"))
        end_name = id_to_name.get(edge.get("endNodeId"))
        if start_name is not None:
            startNodeName = start_name
        if end_name is not None:
            endNodeName = end_name
        edge["edgeName"] = f"{startNodeName} => {endNodeName}"
        processed += 1
        if processed % chunk == 0 or processed == total:
            yield processed, total

    out.append(renamed)


def replaceNodeNamesByStationNames(lif):
    out = []
    for _ in replaceNodeNamesByStationNames_steps(lif, out):
        pass
    return out[0] if out else 0


# Strip all whitespace from node, edge and station names.
def removeWhiteSpaceInNodeEdgeStationName(lif):
    changed = 0
    for node in lif["layouts"][0]["nodes"]:
        new_name = node["nodeName"].replace(" ", "")
        if new_name != node["nodeName"]:
            changed += 1
        node["nodeName"] = new_name

    for edge in lif["layouts"][0]["edges"]:
        new_name = edge["edgeName"].replace(" ", "")
        if new_name != edge["edgeName"]:
            changed += 1
        edge["edgeName"] = new_name

    for station in lif["layouts"][0]["stations"]:
        new_name = station["stationName"].replace(" ", "")
        if new_name != station["stationName"]:
            changed += 1
        station["stationName"] = new_name
    return changed


# Map original nodeId -> nodeName so later id replacements keep resolving.
def buildNodeIdToNameMap(lif):
    # Built once from the original nodeIds so later replacements keep resolving correctly.
    return {
        node["nodeId"]: node.get("nodeName", node["nodeId"])
        for node in lif["layouts"][0]["nodes"]
    }


# Replace each nodeId with its node name using the prebuilt map.
def replaceNodeIdsByNodeNames(lif, node_id_to_name):
    nodes = lif["layouts"][0]["nodes"]
    for node in nodes:
        node["nodeId"] = node_id_to_name.get(node["nodeId"], node["nodeId"])
    return len(nodes)


# Replace edge start/end nodeIds with the corresponding node names.
def replaceEdgeNodeIdsByNodeNames(lif, node_id_to_name):
    edges = lif["layouts"][0]["edges"]
    for edge in edges:
        edge["startNodeId"] = node_id_to_name.get(edge.get("startNodeId"), edge.get("startNodeId"))
        edge["endNodeId"] = node_id_to_name.get(edge.get("endNodeId"), edge.get("endNodeId"))
    return len(edges)


# Replace station interactionNodeIds with the corresponding node names.
def replaceInteractionNodeIdsByNodeNames(lif, node_id_to_name):
    stations = lif["layouts"][0]["stations"]
    for station in stations:
        station["interactionNodeIds"] = [
            node_id_to_name.get(node_id, node_id)
            for node_id in station.get("interactionNodeIds", [])
        ]
    return len(stations)


# Replace each edgeId with its edgeName.
def replaceEdgeIdsByEdgeNames(lif):
    edges = lif["layouts"][0]["edges"]
    for edge in edges:
        edge["edgeId"] = edge.get("edgeName", edge["edgeId"])
    return len(edges)


# Strip the leading "0.0." prefix from every node mapId.
def removeMapIdPrefix(lif):
    changed = 0
    for node in lif["layouts"][0]["nodes"]:
        new_map_id = node["mapId"].removeprefix("0.0.")
        if new_map_id != node["mapId"]:
            changed += 1
        node["mapId"] = new_map_id
    return changed


# Copy each node's name into its description field.
def writeNodeNameToDescription(lif):
    nodes = lif["layouts"][0]["nodes"]
    for node in nodes:
        node["nodeDescription"] = node["nodeName"]
    return len(nodes)


# Create a station for every node whose name contains "park".
def createStationsFromParkNodes(lif, theta):
    layouts = lif.get("layouts", [])

    layout = layouts[0]
    nodes = layout.get("nodes", [])
    stations = layout.setdefault("stations", [])

    created = 0
    for node in nodes:
        node_name = str(node.get("nodeName", ""))
        node_name_lower = node_name.lower()

        if "park" not in node_name_lower:
            continue

        logger.info("Found park nodeName match: %s", node_name)

        station_base_name = node_name.split("_", 1)[0]
        node_position = node.get("nodePosition", {})

        created_station = {
            "stationId": station_base_name,
            "interactionNodeIds": [node.get("nodeId")],
            "stationName": station_base_name,
            "stationDescription": "",
            "stationHeight": 0,
            "stationPosition": {
                "x": node_position.get("x"),
                "y": node_position.get("y"),
                "theta": theta
            }
        }

        stations.append(created_station)
        logger.info("Created station: %s", station_base_name)
        created += 1
    return created


# Return the node matching the given nodeId, or None if not found.
def getNodeById(lif, nodeId):
    for node in lif["layouts"][0]["nodes"]:
        if node["nodeId"] == nodeId:
            return node
    logger.warning("Node not found: %s", nodeId)


# Report any edges or nodes missing vehicleType properties.
def checkEmptyVehicleTypeProperties(lif):
    all_mapped = True

    for edge in lif["layouts"][0]["edges"]:
        if not edge.get("vehicleTypeEdgeProperties"):
            all_mapped = False
            logger.warning("Empty vehicleTypeEdgeProperties: edgeId=%s edgeName=%s",
                           edge.get('edgeId'), edge.get('edgeName'))

    for node in lif["layouts"][0]["nodes"]:
        if not node.get("vehicleTypeNodeProperties"):
            all_mapped = False
            logger.warning("Empty vehicleTypeNodeProperties: nodeId=%s nodeName=%s",
                           node.get('nodeId'), node.get('nodeName'))

    if all_mapped:
        logger.info("All edges and nodes have vehicleType properties mapped.")
    return all_mapped


# Apply the enabled transformations to an already-parsed LIF dict (in place).
# Returns True if the pipeline ran, False if it aborted on missing vehicleType properties.
# Yielded by iter_transformations when the vehicleType check fails.
ABORT = object()


# Number of transformation steps that will run, to size a progress bar.
# Must stay in sync with the enabled blocks in iter_transformations().
def count_enabled_steps(options):
    count = 0
    if options.fix_control_points_order:
        count += 1
    if options.replace_node_names_by_station_names:
        count += 1
    if options.remove_action_param:
        count += 1
    if options.remove_edge_prop:
        count += 1
    if options.write_node_name_to_description:
        count += 1
    if options.create_rack_offset:
        count += 1
    if options.remove_whitespace:
        count += 1
    if options.remove_map_id_prefix:
        count += 1
    if options.create_stations_from_park_nodes:
        count += 1
    if options.replace_ids_by_names:
        count += 1
    return count


# Run the enabled transformations one at a time, yielding a label BEFORE each
# step runs so a caller can repaint progress between steps. Yields ABORT (and
# stops) if any node/edge is missing vehicleType properties.
def iter_transformations(output_data, options):
    # Always report missing vehicleType properties.
    if not checkEmptyVehicleTypeProperties(output_data):
        logger.error("Aborting: some nodes/edges are missing vehicleType properties.")
        yield ABORT
        return

    layout = output_data["layouts"][0]
    total_nodes = len(layout.get("nodes", []))
    total_edges = len(layout.get("edges", []))
    total_stations = len(layout.get("stations", []))
    total_names = total_nodes + total_edges + total_stations

    logger.info("Input: %d nodes, %d edges, %d stations", total_nodes, total_edges, total_stations)

    if options.fix_control_points_order:
        yield "Fixing order of trajectory control points"
        count = fixOrderOfControlPoints(output_data)
        logger.info("Fixed order of control points on %d/%d %s "
                    "in edges[].vehicleTypeEdgeProperties[0].trajectory.controlPoints",
                    count, total_edges, plural(count, "edge"))
    if options.replace_node_names_by_station_names:
        yield "Renaming interaction nodes/edges to station names"
        out = []
        for i, sub_total in replaceNodeNamesByStationNames_steps(output_data, out):
            yield ("sub", i, sub_total)
        count = out[0] if out else 0
        logger.info("Replaced node names by station names on %d/%d %s "
                    "in nodes[].nodeName, edges[].edgeName", count, total_nodes, plural(count, "node"))
    if options.remove_action_param:
        yield "Removing action parameter keys"
        for param_key in options.remove_action_param:
            count = removeNodeActionParameter(output_data, param_key)
            logger.info("Removed action parameter '%s' from %d %s "
                        "in nodes[].vehicleTypeNodeProperties[].actions[].actionParameters[].%s",
                        param_key, count, plural(count, "action"), param_key)
    if options.remove_edge_prop:
        yield "Removing vehicleTypeEdgeProperties keys"
        for property_key in options.remove_edge_prop:
            count = removeVehicleTypeEdgeProperties(output_data, property_key)
            logger.info("Removed edge property '%s' from %d %s "
                        "in edges[].vehicleTypeEdgeProperties[].%s",
                        property_key, count, plural(count, "entry", "entries"), property_key)
    if options.write_node_name_to_description:
        yield "Copying node names into descriptions"
        count = writeNodeNameToDescription(output_data)
        logger.info("Wrote node names to descriptions on %d/%d %s "
                    "in nodes[].nodeDescription", count, total_nodes, plural(count, "node"))
    if options.create_rack_offset:
        yield "Offsetting stacked rack station nodes"
        out = []
        for i, sub_total in createRackOffset_steps(output_data, out):
            yield ("sub", i, sub_total)
        count = out[0] if out else 0
        logger.info("Created rack offsets on %d/%d %s "
                    "in nodes[].nodePosition.x", count, total_nodes, plural(count, "node"))
    if options.remove_whitespace:
        yield "Removing whitespace from names"
        count = removeWhiteSpaceInNodeEdgeStationName(output_data)
        logger.info("Removed whitespace from %d/%d %s "
                    "in nodes[].nodeName, edges[].edgeName, stations[].stationName",
                    count, total_names, plural(count, "name"))
    if options.remove_map_id_prefix:
        yield "Removing map id prefix"
        count = removeMapIdPrefix(output_data)
        logger.info("Removed map id prefix from %d/%d %s in nodes[].mapId", count, total_nodes, plural(count, "node"))
    if options.create_stations_from_park_nodes:
        yield "Creating stations from park nodes"
        count = createStationsFromParkNodes(output_data, theta=options.park_theta)
        logger.info("Created %d %s from park nodes in stations[]", count, plural(count, "station"))
    # Id-to-name replacement runs last so earlier id-based lookups still resolve.
    if options.replace_ids_by_names:
        yield "Replacing ids with names"
        node_id_to_name = buildNodeIdToNameMap(output_data)
        edge_count = replaceEdgeNodeIdsByNodeNames(output_data, node_id_to_name)
        interaction_count = replaceInteractionNodeIdsByNodeNames(output_data, node_id_to_name)
        node_count = replaceNodeIdsByNodeNames(output_data, node_id_to_name)
        edge_id_count = replaceEdgeIdsByEdgeNames(output_data)
        station_count = replaceStationIdsByNames(output_data)
        logger.info("Replaced node ids by names on %d/%d %s in nodes[].nodeId",
                    node_count, total_nodes, plural(node_count, "node"))
        logger.info("Replaced edge start/end node ids by names on %d/%d %s "
                    "in edges[].startNodeId, edges[].endNodeId",
                    edge_count, total_edges, plural(edge_count, "edge"))
        logger.info("Replaced edge ids by names on %d/%d %s in edges[].edgeId",
                    edge_id_count, total_edges, plural(edge_id_count, "edge"))
        logger.info("Replaced station ids by names on %d/%d %s in stations[].stationId",
                    station_count, total_stations, plural(station_count, "station"))
        logger.info("Replaced station interaction ids by names on %d/%d %s "
                    "in stations[].interactionNodeIds[]",
                    interaction_count, total_stations, plural(interaction_count, "station"))


# Synchronous wrapper: run all enabled transformations. Returns False if the
# vehicleType check aborts, True otherwise.
def apply_transformations(output_data, options):
    for item in iter_transformations(output_data, options):
        if item is ABORT:
            return False
    return True
