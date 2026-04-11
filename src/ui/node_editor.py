import dearpygui.dearpygui as dpg
from ui.menu_provider_base import MenuProviderBase


class NodeEditor(MenuProviderBase):
    def __init__(self, parent : str) -> None:
        self._tag : str = "node_editor"
        self._node_count : int = 0
        dpg.add_node_editor(tag=self._tag, parent=parent, callback=self._link, delink_callback=self._delink)


    def _add_node(self, label, attr_in, attr_out, width) -> None:
        with dpg.node(label=label, parent=self._tag):
            with dpg.node_attribute(label=attr_in):
                dpg.add_input_float(label="F", width=width)
            with dpg.node_attribute(label=attr_out, attribute_type=dpg.mvNode_Attr_Output):
                dpg.add_input_float(label="F", width=width)


    def _link(self, sender, app_data) -> None:
        dpg.add_node_link(app_data[0], app_data[1], parent=sender)


    def _delink(self, sender, app_data) -> None:
        dpg.delete_item(app_data)


    def add_menu(self, parent_tag : str) -> None:
        with dpg.menu(label="Node Editor", parent=parent_tag, tag="node_editor_menu"):
            dpg.add_menu_item(label="Add Node", callback=self._on_add_node)
            dpg.add_menu_item(label="Clear All", callback=self._on_clear_nodes)


    def _on_add_node(self, sender) -> None:
        self._node_count += 1
        n = self._node_count
        self._add_node(label=f"Node {n}", attr_in=f"attr_in_{n}", attr_out=f"attr_out_{n}", width=200)


    def _on_clear_nodes(self, sender) -> None:
        child_nodes = dpg.get_item_children("node_editor", 1)
        if child_nodes is None:
            return
        
        for child in child_nodes:
            dpg.delete_item(child)

