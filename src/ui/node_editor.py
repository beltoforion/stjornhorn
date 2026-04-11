import dearpygui.dearpygui as dpg
from ui.menu_provider_base import MenuProviderBase


class NodeEditor(MenuProviderBase):
    def __init__(self, parent : str) -> None:
        self._tag : str = "node_editor"
        self._build_demo_nodes(parent)
   
    
    def _build_demo_nodes(self, parent_tag : str) -> None:
        with dpg.node_editor(tag=self._tag, parent=parent_tag, callback=self._link, delink_callback=self._delink):
            self._add_node(label="Node 1", attr_in="A1", attr_out="A2", width=200)
            self._add_node(label="Node 2", attr_in="A3", attr_out="A4", width=200)


    def _add_node(self, label, attr_in, attr_out, width) -> None:
        with dpg.node(label=label):
            with dpg.node_attribute(label=attr_in):
                dpg.add_input_float(label="F", width=width)
            with dpg.node_attribute(label=attr_out, attribute_type=dpg.mvNode_Attr_Output):
                dpg.add_input_float(label="F", width=width)


    def _link(self, sender, app_data) -> None:
        dpg.add_node_link(app_data[0], app_data[1], parent=sender)


    def _delink(self, sender, app_data) -> None:
        dpg.delete_item(app_data)


    def add_menu(self, parent_tag : str) -> None:
        with dpg.menu(label="Node Editor", parent=parent_tag):
            dpg.add_menu_item(label="Add Node", callback=self._on_add_node)
            dpg.add_menu_item(label="Clear All", callback=self._on_clear_nodes)


    def _on_add_node(self, sender) -> None:
        print(f"Add Node: {sender}")


    def _on_clear_nodes(self, sender) -> None:
        child_nodes = dpg.get_item_children("node_editor", 1)
        if child_nodes is None:
            return
        
        for child in child_nodes:
            dpg.delete_item(child)

