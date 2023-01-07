from collections import OrderedDict

from PyQt5.QtCore import QObject, pyqtSignal

class region_view_signals(QObject):
    instance_selection_changed = pyqtSignal()
    keybinding_changed = pyqtSignal()

class region_view_ctl():
    """This is the handling class of all region_view class events. This class
    could be considered the model of the view"""

    def __init__(self, region : str, instances : list,
                 interfaces : dict, inst_row_len : int, signals : region_view_signals) -> None:

        self.region = region
        self.instances = instances
        self.interfaces = interfaces
        self.signals = signals;
        self.instances_row_len = inst_row_len

        self.chosen_instance_ix = 0
        self.previous_selected_instance = None
        self.keybindings_menu_stack = list()

        self._configure_keybindings()


    def get_selected_instance(self) -> int|None:
        """ returns the instance which needs to be marked"""
        if not len(self.instances):
            return None

        return self.chosen_instance_ix


    def get_previously_selected_instance(self) -> int|None:
        """ returns the instance which was previously selected and now need to
        be unmarked"""
        return self.previous_selected_instance


    def get_instances_list(self) -> list:
        """Get dictionary representing the instances"""
        return self.instances


    def _add_keybinding_submenu(self, kb_menu : dict, kb_submenu : dict, desc :
                                str, key : str):

        def set_submenu(new_menu : dict):
            self.keybindings_menu_stack.append(new_menu)
            self.signals.keybinding_changed.emit()

        kb_menu[key] = {
            "desc" : desc,           
            "func" : lambda kb_menu=kb_submenu : set_submenu(kb_menu)
        }

        # add a keybinding to return to prev menu
        def go_prev_kb_menu():
            self.keybindings_menu_stack.pop()
            self.signals.keybinding_changed.emit()

        self._add_keybind(kb_submenu, "cancel", "c", [], go_prev_kb_menu)


    def get_current_kb_menu(self) -> dict:
        """Return current keybindings"""
        return self.keybindings_menu_stack[-1]


    def _add_keybind(self, kb_menu : dict, desc : str, key : str, aliases : list, func):
        kb_menu[key] = {
            "desc" : desc,
            "func" : func,
        }

        for a in aliases:
            kb_menu[a] = kb_menu[key]


    def __changed_selected_instance(self, amount):
        new_selected = self.chosen_instance_ix + amount
        new_selected %= len(self.instances)

        # in case we're ended up marking same instance, make sure no previous
        # instance needs to be unselected
        if new_selected == self.chosen_instance_ix:
            self.previous_selected_instance = None
            return

        self.previous_selected_instance = self.chosen_instance_ix
        self.chosen_instance_ix = new_selected
        self.signals.instance_selection_changed.emit()

        # print("previous_selected_instance:", self.previous_selected_instance)
        # print("new selected:", self.chosen_instance_ix)
        # print("advancing amount:", amount)


    def _configure_keybindings(self):
        root_kb = dict()

        # instance selection movement
        rl = self.instances_row_len
        for keys, amount in \
            [ ["h", -1] , ["j", -rl], ["k", rl], ["l", 1] ]:
            func = lambda a=amount:  self.__changed_selected_instance(a)
            self._add_keybind(root_kb, "", keys, [], func)

        instances_menu = dict()
        self._add_keybinding_submenu(root_kb, instances_menu, "instances", "i")

        self.keybindings_menu_stack.append(root_kb)


    def keyPressedEvent(self, e):
        letter = e.text()

        kb_menu = self.keybindings_menu_stack[-1]

        if letter not in kb_menu:
            return

        kb = kb_menu[letter]
        func = kb["func"]

        func()
