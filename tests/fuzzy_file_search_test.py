
import sys
from os import path
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication, QSpacerItem, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

# dirty hack allowing the test to be triggerred as stand alone application and
# still be able to access all modules in repo
file_dir = path.dirname(path.realpath(__file__))
main_dir = path.dirname(file_dir)
sys.path.append(main_dir)

from gui.fuzzy_list_search import fuzzy_list_search

class fuzzy_list_search_test(QWidget):
    def __init__(self):
        super().__init__()
        
        self.setGeometry(50, 200, 900, 900)
        self.setWindowTitle("Fuzzy file search test")

        win_layout = QVBoxLayout()

        self.fuzzy_list_search = fuzzy_list_search(lazy_init=False)

        win_layout.addWidget(self.fuzzy_list_search)

        spacer = QSpacerItem(0, 0, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        win_layout.addSpacerItem(spacer)

        self.setLayout(win_layout)

        self.show()

        options = [
            "cucambers",
            "apples",
            "bannanas",
            "sage",
            "oranges"
        ]

        self.fuzzy_list_search.multiline_selection("Choose fruit:", options)
        self.setFocus()

        # self.close()

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key.Key_Escape or e.text() == 'q':
            self.close()


def test():
    app = QApplication(sys.argv)
    
    # for some reason, not assigning the return value to a variable
    # makes the program stuck on load
    window = fuzzy_list_search_test() # pyright: ignore

    sys.exit(app.exec())


if __name__ == '__main__':
    test()
