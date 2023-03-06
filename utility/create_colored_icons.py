import os
from xml.dom import minidom

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
icon_folder = os.path.join(root_dir, "anchor", "resources")

base_folder = os.path.join(icon_folder, "base_tool_buttons")
checked_folder = os.path.join(icon_folder, "checked_tool_buttons")
disabled_folder = os.path.join(icon_folder, "disabled_tool_buttons")
hover_folder = os.path.join(icon_folder, "hover_tool_buttons")

folders = {
    "base": os.path.join(icon_folder, "base_tool_buttons"),
    "hover": os.path.join(icon_folder, "hover_tool_buttons"),
    "disabled": os.path.join(icon_folder, "disabled_tool_buttons"),
    "checked": os.path.join(icon_folder, "checked_tool_buttons"),
    "highlighted": os.path.join(icon_folder, "highlighted_tool_buttons"),
}

colors = {
    "base": "#001D3D",  # dark blue
    "hover": "#FFD60A",  # light yellow
    "disabled": "#C63623",  # light red
    "checked": "#FFD60A",  # light yellow
    "highlighted": "#0E63B3",  # very light blue
}


def create_icon_set(identifier):
    color = colors[identifier]
    out_dir = folders[identifier]
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(base_folder):
        print(f)
        base_path = os.path.join(base_folder, f)
        out_path = os.path.join(out_dir, f)
        doc = minidom.parse(base_path)
        path = doc.getElementsByTagName("path")
        width = float(doc.getElementsByTagName("svg")[0].getAttribute("viewBox").split()[2])
        for p in path:
            print(dir(p))
            print(p.getAttribute("fill"))
            p.setAttribute("fill", color)
            print(p.getAttribute("stroke"))
            p.setAttribute("stroke", color)
            p.setAttribute("stroke-width", str(2 * width / 100))
        print(path)

        with open(out_path, "w", encoding="utf8") as f:
            doc.writexml(f)


create_icon_set("base")
create_icon_set("hover")
create_icon_set("disabled")
create_icon_set("checked")
create_icon_set("highlighted")
