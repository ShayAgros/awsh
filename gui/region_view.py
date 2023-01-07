from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget

from gui.instance import ec2_instance
from gui.region_view_ctrl import region_view_ctl, region_view_signals

INSTANCES_VIEW_ROW_LEN = 4

class region_view(QWidget):
    """Lists the insatnces and operations in a specific region"""

    def __init__(self, region, region_long_name, instances : list,
                 interfaces : dict):
        super().__init__()

        # Instantiate metadata

        self.region = region
        self.region_long_name = region_long_name
        self.signals = region_view_signals()
        self.ctl = region_view_ctl(region, instances, interfaces,
                                   INSTANCES_VIEW_ROW_LEN, self.signals)

        # draw the GUI part
        self.createUpperLayout()
        self.createInstancView()
        self.createInstanceDesc()
        self.createKeyBindingDesc()
        self.createMessagePane()

        win_layout = QVBoxLayout()

        win_layout.addWidget(self.upper_widget)
        win_layout.addWidget(self.instances_view_container)
        win_layout.addWidget(self.instance_desc)
        win_layout.addWidget(self.keybinding_container)
        win_layout.addWidget(self.msg_list)


        self.setLayout(win_layout)

        # mark first instance and update description
        self.update_instance_selection()
        self.connectSlots()


    def createUpperLayout(self):
        font = QFont("FiraCode Nerd Font Mono", 16)
        region_str = f"{self.region} | {self.region_long_name}"
        region_label = QLabel(region_str)
        region_label.setFont(font)
        region_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        region_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                   QtWidgets.QSizePolicy.Policy.Fixed)

        self.upper_widget = region_label


    def createInstancView(self):
        glayout = QGridLayout()
        glayout.setContentsMargins(15, 15, 15, 15)
        glayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) # type: ignore
        glayout.setSpacing(20)

        i = 0
        row_len = INSTANCES_VIEW_ROW_LEN

        instances_widgets = []
        for instance in self.ctl.get_instances_list():
            ins_widget = ec2_instance(instance, self.region)
            glayout.addWidget(ins_widget, i // row_len,  i % row_len)

            instances_widgets.append(ins_widget)
            i = i + 1


        instances_view_container = QWidget()
        instances_view_container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                               QtWidgets.QSizePolicy.Policy.Expanding)
        instances_view_container.setLayout(glayout)

        self.instances_widgets = instances_widgets
        self.instances_view = glayout
        self.instances_view_container = instances_view_container

        # mark the first instance
        # self.update_instance_selection()


    def _add_widget_pair(self, fwidget : QWidget, swidget : QWidget):
        """Creates a horizonal layout of widget pairs"""
        pair_layout = QHBoxLayout()
        pair_layout.setSpacing(6)
    
        pair_layout.addWidget(fwidget)
        pair_layout.addWidget(swidget)

        pair_widget = QWidget()
        pair_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                  QtWidgets.QSizePolicy.Policy.Fixed)
        pair_widget.setLayout(pair_layout)

        return pair_widget


    def _updateInstanceDesc(self):
        ctl = self.ctl

        instance_ix = ctl.get_selected_instance()
        if instance_ix is None:
            return

        instance = ctl.get_instances_list()[instance_ix]

        for desc_label in self.desc_labels:
            val_widget = desc_label["val_widget"]
            ins_attr = desc_label["instance_attr"]

            if ins_attr is None:
                continue

            val_widget.setText(instance[ins_attr])


    def createInstanceDesc(self):

        desc_layout = QGridLayout()
        desc_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        desc_labels = list()

        i = 0
        label_pairs = [
            ["id", "id"], ["ami", "ami_id"], ["az", "az"], ["os", None], ["size", "instance_type"]
        ]
        for label_pair in label_pairs:
            label_desc = label_pair[0]
            instance_attr = label_pair[1]

            label_desc_widget = QLabel(f"{label_desc}:")
            label_desc_widget.setObjectName("label")
            label_val_widget = QLabel()
            label_desc_widget.setBuddy(label_val_widget)

            pwidget = self._add_widget_pair(label_desc_widget, label_val_widget)
            desc_layout.addWidget(pwidget, 0, i)

            desc_label = {
                "val_widget" : label_val_widget,
                "instance_attr" : instance_attr
            }
            desc_labels.append(desc_label)

            i = i + 1

        desc_frame = QFrame()
        desc_frame.setStyleSheet(""" 
            .QFrame {
                border-style: solid;
                border-color: black;
                border-top-width: 2px;
                border-bottom-width: 2px;
            }

            QLabel#label {
                color: #FA5151;
                font-style: italic
            }
        """)

        desc_frame.setLayout(desc_layout)

        self.desc_labels = desc_labels
        self.instance_desc = desc_frame


    def _createKeyBindingLabel(self, kb_str : str, kb_highlighted_letter : str):
        kb_format_str = kb_str

        highlight_letter_ix = kb_str.find(kb_highlighted_letter)
        # the highlighed letter is in the string
        if highlight_letter_ix >=0:
            kb_format_str = kb_str[0:highlight_letter_ix]
            kb_format_str += '<span style="color: red ">' + kb_highlighted_letter + '</span>'
            if highlight_letter_ix + 1 < len(kb_str):
                kb_format_str += kb_str[highlight_letter_ix + 1:]

        kb_label = QLabel(kb_format_str)

        return kb_label


    def _add_keybinding_labels(self, containing_widget):
        kb_layout = QHBoxLayout()

        keys_label = QLabel("keys:")
        keys_label.setStyleSheet("""
            font-style: italic;
            color: #29B306
        """)

        kb_layout.addWidget(keys_label)

        for key, kb_conf in self.ctl.get_current_kb_menu().items():
            desc = kb_conf["desc"]
            # "hidden" keybindings
            if not desc:
                continue

            kb_label = self._createKeyBindingLabel(desc, key)
            kb_layout.addWidget(kb_label)

        containing_widget.setLayout(kb_layout)


    # slot function
    def update_keybinding_menu(self):
        kb_container = QWidget()
        kb_container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                   QtWidgets.QSizePolicy.Policy.Fixed)
        kb_container.setStyleSheet("""
            QLabel {
                font-size: 13px
            }
        """)

        self._add_keybinding_labels(kb_container)

        # if the function is called to *update* keybinding menu, make sure to
        # remove the previous one
        if self.keybinding_container is not None:
            original_container = self.keybinding_container
            parent = original_container.parentWidget()
            layout = parent.layout()

            prev_widget = layout.replaceWidget(original_container, kb_container)
            prev_widget.widget().deleteLater()

        self.keybinding_container = kb_container


    def createKeyBindingDesc(self):
        # this would identify it as the first time we draw it
        self.keybinding_container = None
        self.update_keybinding_menu()


    def createMessagePane(self):
        msg_list = QListWidget()
        msg_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        msg_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                               QtWidgets.QSizePolicy.Policy.Minimum)

        self.msg_list = msg_list


    def connectSlots(self):
        signals = self.signals
        signals.instance_selection_changed.connect(self.update_instance_selection)
        signals.keybinding_changed.connect(self.update_keybinding_menu)

    # slot function
    def update_instance_selection(self):
        ctl = self.ctl
        selected_ix = ctl.get_selected_instance()
        prev_selected_ix = ctl.get_previously_selected_instance()

        if selected_ix is not None:
            instance = self.instances_widgets[selected_ix]
            instance.mark()

        if prev_selected_ix is not None:
            instance = self.instances_widgets[prev_selected_ix]
            instance.unmark()

        self._updateInstanceDesc()


    def keyPressEvent(self, e):
        self.ctl.keyPressedEvent(e)
