from typing import Any, List
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QStackedLayout, QVBoxLayout, QWidget
from gui.fuzzy_list_search import fuzzy_list_search

from gui.instance import ec2_instance
from gui.region_view_ctrl import region_view_command_status, region_view_ctl, region_view_signals

INSTANCES_VIEW_ROW_LEN = 4
RUNNING_STATE_CODE = 16
TERMINATED_STATE_CODE = 48

class region_view(QWidget):
    """Lists the insatnces and operations in a specific region"""

    def __init__(self, region : str, region_long_name : str, instances : list,
                 interfaces : dict, subnets : dict):
        super().__init__()

        self.logger = logging.getLogger(f"awsh_region_view_{region}")

        # Instantiate metadata

        self.region = region
        self.region_long_name = region_long_name
        self.signals = region_view_signals()
        # TODO: subnets is probably can be passed in a later phase than
        # initialization. Maybe execute asynchronous call to server to require
        # them after region is displayed
        self.ctl = region_view_ctl(region, instances, interfaces, subnets,
                                   INSTANCES_VIEW_ROW_LEN, self.signals)

        # draw the GUI part
        self.createUpperLayout()
        self.createInstancView()
        self.createInstanceDesc()
        self.createKeyBindingDesc()
        self.createMessagePane()
        self.createOptionsList()

        # this layout will alternate between MessagePane and OptionsList
        self.bottom_stack_layout = None

        win_layout = QVBoxLayout()

        win_layout.addWidget(self.upper_widget)
        win_layout.addWidget(self.instances_view_container)
        win_layout.addWidget(self.instance_desc)
        win_layout.addWidget(self.keybinding_container)
        win_layout.addWidget(self.msg_list)

        self.setLayout(win_layout)

        # mark first instance and update description
        self.ctl.setUI(self.list_search)
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
        self.instances_view_container = None
        self._updateInstancView()

    
    # Slot function
    def _setInstancesIndices(self):
        instances = self.instances_widgets
        instances_indices = self.ctl.getInstancesIndices()
        for i, instance in enumerate(instances):
            if i in instances_indices:
                instance.setIndex(instances_indices[i])
            else:
                instance.clearIndex()


    def setFocus(self):
        self.logger.debug("Explicitly required focus, updating current instances")
        self._setInstancesIndices()
        super().setFocus()


    def _updateInstancView(self):
        glayout = QGridLayout()
        glayout.setContentsMargins(15, 15, 15, 15)
        glayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) # type: ignore
        glayout.setSpacing(20)

        row_len = INSTANCES_VIEW_ROW_LEN

        instances_widgets : List[ec2_instance] = []
        for i, instance in enumerate(self.ctl.getInstancesList()):
            # if instance["state"]["Code"] != RUNNING_STATE_CODE:
                # continue

            ins_widget = ec2_instance(instance, self.region)
            glayout.addWidget(ins_widget, i // row_len,  i % row_len)

            instances_widgets.append(ins_widget)

        instances_view_container = QWidget()
        instances_view_container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                               QtWidgets.QSizePolicy.Policy.Expanding)
        instances_view_container.setLayout(glayout)

        # replace existing view with the new one
        if self.instances_view_container is not None:
            original_container = self.instances_view_container
            parent = original_container.parentWidget()
            layout = parent.layout()

            prev_widget = layout.replaceWidget(original_container, instances_view_container)
            prev_widget.widget().deleteLater()
            

        # self._setInstancesIndices(instances_widgets)

        self.instances_widgets = instances_widgets
        self.instances_view = glayout
        self.instances_view_container = instances_view_container


    # Slot function
    def updateInstances(self):
        """List of instances has changed, update the instances, their selection
        and their description"""
        self._updateInstancView()
        self.update_instance_selection()
        self._setInstancesIndices()


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

        instance_ix = ctl.getSelectedInstance()
        if instance_ix is None:
            return

        instance = ctl.getInstancesList()[instance_ix]

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
            ["id", "id"], ["ami", "ami_id"], ["az", "az"], ["os", "distro"], ["size", "instance_type"]
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

        for key, kb_conf in self.ctl.getCurrentKbMenu().items():
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


    def set_list_search_visible(self, enable : Any):

        # first time call. Replace the existing msg_list with a stack
        # layout which allows to display the search list as well
        if self.bottom_stack_layout is None:
            # find the previous layout containing msg_list
            msg_list = self.msg_list
            parent = msg_list.parentWidget()
            original_layout = parent.layout()

            bottom_stack_layout = QStackedLayout()

            bottom_stack_container = QWidget()
            bottom_stack_container.setLayout(bottom_stack_layout)

            # replace msg_list with the new stackedLayout containing it
            original_layout.replaceWidget(msg_list, bottom_stack_container)

            bottom_stack_layout.addWidget(self.msg_list)
            bottom_stack_layout.addWidget(self.list_search)

            self.bottom_stack_layout = bottom_stack_layout

        if enable:
            self.bottom_stack_layout.setCurrentIndex(1)
            self.list_search.setFocus()
        else:
            self.bottom_stack_layout.setCurrentIndex(0)
            self.setFocus()



    def createOptionsList(self):
        def fuzzy_list_focus (enable : Any):
            self.set_list_search_visible(enable)

        self.list_search = fuzzy_list_search(set_focus=fuzzy_list_focus,
                                             lazy_init=True)


    def __get_status_string(self, status : region_view_command_status):
        rvcs = region_view_command_status

        if status == rvcs.COMMAND_STATUS_INITIATED:
            # return '<span style="color: blue">Sent </span>'
            # Seems like I can't do inline markup
            return 'Sent'

        if status == rvcs.COMMAND_STATUS_SUCCESS:
            return "Completed"

        if status == rvcs.COMMAND_STATUS_FAILED:
            return "Failed"

        return "Unknown"


    # Slot function
    def _updateMessages(self):
        msg_list = QListWidget()
        msg_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        msg_list.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                               QtWidgets.QSizePolicy.Policy.Minimum)

        msgs = self.ctl.getSubmittedCommands()
        for msg in msgs:
            desc = msg["desc"]
            status = self.__get_status_string(msg["status"])

            list_item = QListWidgetItem(f"{status}: {desc}")
            msg_list.addItem(list_item)

        widget_parent_layout = self.msg_list.parentWidget().layout()
        prev_widget = widget_parent_layout.replaceWidget(self.msg_list, msg_list)
        prev_widget.widget().deleteLater()

        self.msg_list = msg_list


    def connectSlots(self):
        signals = self.signals
        signals.instance_selection_changed.connect(self.update_instance_selection)
        signals.keybinding_changed.connect(self.update_keybinding_menu)
        signals.server_commands_added.connect(self._updateMessages)
        signals.instances_list_changed.connect(self.updateInstances)
        signals.instances_indices_changed.connect(self._setInstancesIndices)


    # slot function
    def update_instance_selection(self):
        ctl = self.ctl
        selected_ix = ctl.getSelectedInstance()
        prev_selected_ix = ctl.getPreviouslySelectedInstance()

        if selected_ix is not None:
            instance = self.instances_widgets[selected_ix]
            instance.mark()

        if prev_selected_ix is not None:
            instance = self.instances_widgets[prev_selected_ix]
            instance.unmark()

        self._updateInstanceDesc()



    def keyPressEvent(self, e):
        handled = self.ctl.keyPressedEvent(e)
        if handled:
            return

        letter = e.text()
        # TODO: remove later
        choices = [
            { 
                "entry" : "apples",
                "submenu" : ("choose type:", ["red", "green", "greenish"])
            },
            "bannanas",
            "cucambers",
            "oranges",
            "sage",
            "watermelon"
        ]
        if letter == "s":
            rc = self.list_search.multiline_selection("Choose a fruit:", choices)
            print("selection returned", rc)

        # if the control size has nothing to do with the key press, pass it to
        # our parent widget (awsh_gui in this case)
        parent = self.parent()
        if parent is not None:
            parent.keyPressEvent(e) # type: ignore
