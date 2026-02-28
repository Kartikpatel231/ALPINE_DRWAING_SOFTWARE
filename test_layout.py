"""Quick test of layout generation."""
from core.layout_engine import generate_layout
from core.parameters import CoilParameters

p = CoilParameters()
layout = generate_layout(p)
print(f"Views: {len(layout.views)}")
for v in layout.views:
    rect = v.geometry["outer_rect"]
    print(f"  {v.label}: offset=({v.offset_x:.0f},{v.offset_y:.0f}) rect={rect}")
print(f"Notes offset: {layout.notes_offset}")
print(f"Title block offset: {layout.title_block_offset}")
print(f"Drawing title: {layout.title_block['drawing_title']}")
