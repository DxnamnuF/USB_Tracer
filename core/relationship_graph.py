import re


def node_id(value):
    text = str(value or "unknown")
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text)
    if not text or text[0].isdigit():
        text = "n_" + text
    return text[:80]


def label(value):
    return str(value or "unknown").replace("\\", "\\\\").replace('"', "'")[:160]


def add_node(nodes, value, kind):
    if not value:
        return None
    nid = node_id(f"{kind}_{value}")
    nodes[nid] = f'{nid} [label="{label(kind + ": " + str(value))}"];'
    return nid


def add_edge(edges, left, right, relation):
    if left and right:
        edges.add(f'{left} -> {right} [label="{label(relation)}"];')


def build_relationship_edges(timeline, summary):
    edges = []
    seen = set()
    for item in summary or []:
        device = item.get("friendly_name") or item.get("device_key")
        serial = item.get("serial")
        for drive in item.get("drive_letters") or []:
            row = {"from": device, "relation": "uses drive letter", "to": drive}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                edges.append(row)
        for volume in item.get("volume_guids") or []:
            row = {"from": device, "relation": "linked to volume", "to": volume}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                edges.append(row)
        for source in item.get("sources") or []:
            row = {"from": device, "relation": "has evidence in", "to": source}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                edges.append(row)
        if serial:
            row = {"from": device, "relation": "has serial", "to": serial}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                edges.append(row)
    for item in timeline or []:
        device = item.get("friendly_name") or item.get("matched_registry_name") or item.get("device_instance_id")
        if item.get("user_label"):
            row = {"from": item.get("user_label"), "relation": "has user artifact for", "to": device}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                edges.append(row)
        if item.get("file_path") and device:
            row = {"from": device, "relation": "referenced by file artifact", "to": item.get("file_path")}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                edges.append(row)
    return edges


def build_graph_dot(timeline, summary):
    nodes = {}
    edges = set()
    for item in summary or []:
        device = add_node(nodes, item.get("friendly_name") or item.get("device_key"), "device")
        serial = add_node(nodes, item.get("serial"), "serial")
        add_edge(edges, device, serial, "serial")
        for drive in item.get("drive_letters") or []:
            add_edge(edges, device, add_node(nodes, drive, "drive"), "drive letter")
        for volume in item.get("volume_guids") or []:
            add_edge(edges, device, add_node(nodes, volume, "volume"), "volume guid")
        for source in item.get("sources") or []:
            add_edge(edges, device, add_node(nodes, source, "source"), "evidence")
    for item in timeline or []:
        device = add_node(nodes, item.get("friendly_name") or item.get("matched_registry_name") or item.get("device_instance_id"), "device")
        if item.get("user_label"):
            add_edge(edges, add_node(nodes, item.get("user_label"), "user"), device, "user artifact")
        if item.get("file_path"):
            add_edge(edges, device, add_node(nodes, item.get("file_path"), "file"), "file artifact")
    lines = ["digraph DFIR_project_Relationships {", "  rankdir=LR;", "  node [shape=box];"]
    lines += ["  " + line for line in nodes.values()]
    lines += ["  " + line for line in sorted(edges)]
    lines.append("}")
    return "\n".join(lines)
