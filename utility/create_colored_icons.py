import os
from xml.dom import minidom


root_dir =os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
icon_folder = os.path.join(root_dir, 'anchor', 'resources')

base_folder = os.path.join(icon_folder, 'base_tool_buttons')
checked_folder = os.path.join(icon_folder, 'checked_tool_buttons')
disabled_folder = os.path.join(icon_folder, 'disabled_tool_buttons')
hover_folder = os.path.join(icon_folder, 'hover_tool_buttons')

folders = {

    'base': os.path.join(icon_folder, 'base_tool_buttons'),
    'hover': os.path.join(icon_folder, 'hover_tool_buttons'),
    'disabled': os.path.join(icon_folder, 'disabled_tool_buttons'),
    'checked': os.path.join(icon_folder, 'checked_tool_buttons'),
    'highlighted': os.path.join(icon_folder, 'highlighted_tool_buttons'),
}

colors = {
    'base': '#01192F',
    'hover': '#FFE819',
    'disabled': '#D43610',
    'checked': '#F9D213',
    'highlighted': '#49A4F7',
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
        path = doc.getElementsByTagName('path')
        for p in path:
            print(dir(p))
            print(p.getAttribute('fill'))
            p.setAttribute('fill', color)
            if p.hasAttribute('stroke'):
                print(p.getAttribute('stroke'))
                p.setAttribute('stroke', color)
        print(path)

        with open(out_path, 'w', encoding='utf8') as f:
            doc.writexml(f)

create_icon_set('base')
create_icon_set('hover')
create_icon_set('disabled')
create_icon_set('checked')
create_icon_set('highlighted')