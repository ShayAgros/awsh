from typing import Any, Callable, List, Union
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFocusEvent, QKeyEvent
from PyQt5.QtWidgets import QAbstractItemView, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTextEdit, QVBoxLayout, QWidget
from awsh_ui import awsh_ui

from utils.sm_algo import get_sw_score

# Display option enum
DO_ENTRY = 0
DO_STRING_MATCH_IX = 1
DO_ENTRY_SCORE = 2
DO_ORIG_IX = 3
DO_COLOR = 4

class fuzzy_list_item(QWidget):
    """A single entry in the options list"""
    def __init__(self, item_str : str, color : str, original_list_ix : int,
                 matching_chars_ix : list = []):
        super().__init__()

        self.item_str = item_str
        self.original_list_ix = original_list_ix
        self.color = color

        self.createFocusArrow()
        self.createEntryColor()
        self.createItemLabel(matching_chars_ix)

        item_layout = QHBoxLayout()
        item_layout.addWidget(self.arrow_label)
        item_layout.addWidget(self.color_label)
        item_layout.addWidget(self.item_label)

        self.setLayout(item_layout)

    def createEntryColor(self):
        color_label = QLabel("    ")
        color_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                  QtWidgets.QSizePolicy.Policy.Fixed)

        color_label.setStyleSheet(f'background-color: {self.color}')

        self.color_label = color_label

    def createFocusArrow(self):
        arrow_label = QLabel(" ")

        arrow_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                  QtWidgets.QSizePolicy.Policy.Fixed)

        arrow_label.setStyleSheet("""
            color: red
        """)

        self.arrow_label = arrow_label


    def createItemLabel(self, matching_chars_ix : list):
        """Produce markup string label for the @self.item_str and
        put in red all the indices of the string in @matching_char
        list"""
        item_str = self.item_str

        last_marked_ix = 0
        markup_str = ""
        red_css_format = '<span style="color: red ">{}</span>'
        for ix in matching_chars_ix:
            if ix > 0:
                markup_str = markup_str + item_str[last_marked_ix:ix]

            markup_str = markup_str + red_css_format.format(item_str[ix])

            last_marked_ix = ix + 1

        markup_str = markup_str + item_str[last_marked_ix:]

        self.item_label = QLabel(markup_str)


    def setSelected(self, enabled):
        if enabled:
            self.arrow_label.setText(">")
        else:
            self.arrow_label.setText(" ")


    def getListOriginalIndex(self):
        return self.original_list_ix


def no_focus_needed(_):
    pass


class fuzzy_list_search(QDialog, awsh_ui):
    """A list in which one can fuzzy search for results. The list
    uses Smith–Waterman algorithm for sequence alignment"""

    def __init__(self, lazy_init = False,
                 set_focus : Callable[[Any], None] = no_focus_needed) :

        self.list_items = []
        self.lazy_init = lazy_init
        self.current_selected_ix = 0
        self.parent_set_focus = set_focus

        if lazy_init:
            return

        # override it temporarily. This value is gonna be changed back by
        # init_gui(). This allows init_gui() to be called after __init__ as well
        self.lazy_init = True
        self._init_gui()


    def _init_gui(self):
        if not self.lazy_init:
            return

        super().__init__()

        self.createTextSearch()
        self.createOptionsList()

        win_layout = QVBoxLayout()
        win_layout.addWidget(self.search_container)
        win_layout.addWidget(self.msg_list)

        self.setLayout(win_layout)

        self.setWindowFlag(Qt.WindowType.Widget)
        self.lazy_init = False


    def createSearchLabel(self):
        search_label = QLabel()

        search_label.setStyleSheet("""
            QLabel { color: #91dadc }
        """)

        self.search_label = search_label

    def createSearchBox(self):
        text_search = QTextEdit()

        # make the search a single line
        font = text_search.fontMetrics()
        row_len = font.lineSpacing()
        text_search.setFixedHeight(2 * row_len)

        text_search.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                  QtWidgets.QSizePolicy.Policy.Fixed)

        text_search.setStyleSheet("""
            QTextEdit { background: transparent }
                                  """)

        text_search.textChanged.connect(lambda: self.text_search_pattern_changed())

        # override the key press handler to capture Enter key
        def qtextedit_key_press_handler(e : QKeyEvent):
            if e.key() == Qt.Key.Key_Return or e.key() == Qt.Key.Key_Escape:
                return self.keyPressEvent(e)
            if (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                return self.keyPressEvent(e)

            return QTextEdit.keyPressEvent(text_search, e)

        text_search.keyPressEvent = qtextedit_key_press_handler

        self.search_box = text_search


    def createTextSearch(self):
        self.createSearchLabel()
        self.createSearchBox()

        layout = QHBoxLayout()
        layout.addWidget(self.search_label)
        layout.addWidget(self.search_box)

        container = QWidget()
        container.setLayout(layout)

        self.search_container = container


    def _get_list_item_entry_str(self, entry : Union[str, dict]) -> str:
        if type(entry) is str:
            return entry

        if type(entry) is not dict:
            raise Exception("Entries can only be strings or dict")

        if "entry" not in entry:
            raise Exception("dict entries should have 'entry' key")

        if type(entry["entry"]) is not str:
            raise Exception("entry key should be of type string")

        return entry["entry"]


    def _get_display_options(self, pattern : str) -> list:
        """Receieves a pattern and returns all entries which should be
        displayed. If the pattern is emtpy then all the items are being
        displayed, otherwise only items which fuzzy match the pattern are
        displayed"""

        display_options = []
        # If there is a pattern then display all values
        if not pattern:
            for ix, item in enumerate(self.list_items):
                color = ""
                if type(item) == dict and "color" in item:
                    color = item["color"]

                display_option = []
                display_option.insert(DO_ENTRY, self._get_list_item_entry_str(item))
                display_option.insert(DO_STRING_MATCH_IX, [])
                display_option.insert(DO_ENTRY_SCORE, 0)
                display_option.insert(DO_ORIG_IX, ix)
                display_option.insert(DO_COLOR, color)
                display_options.append(display_option)

            return display_options

        # pattern exist
        for ix, item in enumerate(self.list_items):
            item_str = self._get_list_item_entry_str(item)
            _, _, max_sum, string_match_ix = get_sw_score(item_str, pattern,
                                                          pattern_match_required=True,
                                                          retain_pat_order=True)
            # only leave matched options
            if max_sum == 0:
                continue

            # find first item that is smaller and insert on its left
            # (insert into sorted list)
            # This is done in a C style manner and not with range to
            # make sure that if we passed the whole array 'i' equals to
            # sizeof(display_len) and not the last valid index
            i = 0
            display_len = len(display_options)
            while i < display_len:
                if display_options[i][DO_ENTRY_SCORE] < max_sum:
                    break

                i = i + 1

            color = ""
            if type(item) == dict and "color" in item:
                color = item["color"]

            display_option = list()
            display_option.insert(DO_ENTRY, item_str)
            display_option.insert(DO_STRING_MATCH_IX, string_match_ix)
            display_option.insert(DO_ENTRY_SCORE, max_sum)
            display_option.insert(DO_ORIG_IX, ix)
            display_option.insert(DO_COLOR, color)
            display_options.append(display_option)

        return display_options


    # Slot function for when the text of the pattern changed
    def text_search_pattern_changed(self):
        pattern = self.search_box.toPlainText()

        displays_options = self._get_display_options(pattern)

        msg_list = QListWidget()
        msg_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        msg_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        msg_list.setStyleSheet("""
            QListWidget { background: transparent }
                                  """)
        
        for item_pair in displays_options:
            item = QListWidgetItem()

            item_widget = fuzzy_list_item(item_pair[DO_ENTRY],
                                          item_pair[DO_COLOR],
                                          item_pair[DO_ORIG_IX],
                                          item_pair[DO_STRING_MATCH_IX])
            item.setSizeHint(item_widget.sizeHint())

            msg_list.addItem(item)
            msg_list.setItemWidget(item, item_widget)


        if len(displays_options) > 0:
            self.current_selected_ix = 0
            msg_list.itemWidget(msg_list.item(0)).setSelected(True)

        # replace the previous list with the new one
        if not self.first_init:
            original_list = self.msg_list
            parent = original_list.parentWidget()
            layout = parent.layout()

            prev_widget = layout.replaceWidget(original_list, msg_list)
            prev_widget.widget().hide()
            prev_widget.widget().deleteLater()

        self.msg_list = msg_list


    def multiline_selection(self, title : str, choices : List):
        # GUI hasn't been initialized
        if self.lazy_init:
            self._init_gui()

        self.list_items = choices
        self.parent_set_focus(True)

        self.search_label.setText(title)
        self.search_box.setText("")

        chosen_entries = list()

        while True:
            rc = self.exec()
            # user exited abonormaly
            if rc == 1:
                self.parent_set_focus(False)
                return False, None

            # user chose an entry
            entry_widget = self.get_fuzzy_list_item(self.current_selected_ix)
            if entry_widget is None:
                # no entry selected, same as cacneling
                self.parent_set_focus(False)
                return False, None

            chosen_ix = entry_widget.getListOriginalIndex()
            chosen_entries.append(chosen_ix)

            original_entry = self.list_items[chosen_ix]
            # no sublists exist
            if type(original_entry) == str:
                break

            # lunch new list search for the new list
            if type(original_entry) is not dict:
                raise Exception("Entry can only be string or dictionary")

            if "submenu" not in original_entry:
                break

            submenu = original_entry["submenu"]
            if type(submenu) is not tuple or len(submenu) != 2:
                raise Exception("submenu type should be tuple of length 2")

            if (type(submenu[0]) is not str) or (type(submenu[1]) is not list):
                raise Exception("sublist has to be of the form ( str, list ) ")

            self.search_label.setText(original_entry["submenu"][0])
            self.list_items = original_entry["submenu"][1]
            self.search_box.setText("")

        self.parent_set_focus(False)

        return True, chosen_entries


    def createOptionsList(self):
        self.first_init = True
        self.text_search_pattern_changed()
        self.first_init = False


    def focusInEvent(self, _ : QFocusEvent):
        # propagate the focus to the text search
        self.search_box.setFocus()


    def get_fuzzy_list_item(self, index : int) -> Union[fuzzy_list_item, None]:
        msg_list = self.msg_list
        assert msg_list is not None

        # We might be pressing enter but the the item isn't displayed
        # (e.g. if the pattern matches no entries)
        if index > len(msg_list):
            return None

        return msg_list.itemWidget(msg_list.item(index))


    def select_entry(self, entry_ix : int, prev_ix : Union[int, None]):
        entry_widget = self.get_fuzzy_list_item(entry_ix)
        assert entry_widget is not None

        entry_widget.setSelected(True)

        if prev_ix is not None:
            prev_widget = self.get_fuzzy_list_item(prev_ix)
            assert prev_widget is not None

            prev_widget.setSelected(False)

        self.current_selected_ix = entry_ix


    def move_selected(self, amount : int):
        num_options = len(self.msg_list)
        if not num_options:
            return

        prev_sel = self.current_selected_ix
        new_sel = (prev_sel + amount) % num_options

        if prev_sel == new_sel:
            return

        self.select_entry(new_sel, prev_sel)
        pass


    def keyPressEvent(self, e : QKeyEvent):
        # control is pressed
        if (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if e.key() == Qt.Key.Key_U:
                self.search_box.setText("")
            elif e.key() == Qt.Key.Key_N:
                self.move_selected(1)
            elif e.key() == Qt.Key.Key_P:
                self.move_selected(-1)
            elif e.key() == Qt.Key.Key_C:
                self.done(1)

        if e.key() == Qt.Key.Key_Return:
            self.done(0)
            return

        if e.key() == Qt.Key.Key_Escape:
            self.done(1)
