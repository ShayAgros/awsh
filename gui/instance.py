from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

from awsh_utils import awsh_get_subnet_color

RUNNING_STATE_CODE = 16
TERMINATED_STATE_CODE = 48


class ec2_instance(QWidget):
    """Representation of an EC2 instance"""

    stopped_state_color = "#d62728"
    running_state_color  = "#2ca02c"
    
    not_selected_border_color = "#7f7f7f"
    selected_border_color = "#1f77b4"

    def __init__(self, instance : dict, region : str):

        super().__init__()

        # Instantiate metadata

        self.instance = instance
        self.region = region

        # draw the GUI part

        win_layout = QVBoxLayout()
        win_layout.setSpacing(1)

        self.createUpperLayout()
        self.createBottomLayout()

        win_layout.addWidget(self.upper_container)
        win_layout.addWidget(self.bottom_container)

        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                           QtWidgets.QSizePolicy.Policy.Fixed)

        self.setLayout(win_layout)


    def createUpperLayout(self):
        # Instance connection index
        label_policy = (QtWidgets.QSizePolicy.Policy.Fixed,
                        QtWidgets.QSizePolicy.Policy.Fixed)

        instance = self.instance

        ins_ix_label = QLabel("-")
        ins_ix_label.setSizePolicy(*label_policy)
        ins_ix_label.setMinimumWidth(QLabel("99").sizeHint().width())

        instance_state_indicator = QLabel("    ")
        instance_state = True if self.instance["state"]["Name"] == "running" else False
        instance_state_indicator.setProperty("running", instance_state)
        instance_state_indicator.setStyleSheet(f"""
            *[running="false"] {{ background-color: {self.stopped_state_color} }}
            *[running="true"] {{ background-color: {self.running_state_color} }}
            * {{
                border-radius: 4px;
            }}
            """)
        instance_state_indicator.setSizePolicy(*label_policy)

        instance_desc = QLabel()
        tag_name = instance["name"] if instance["name"] != "" else instance["id"]
        instance_desc.setText(tag_name)

        upper = QHBoxLayout()
        upper.addWidget(ins_ix_label)
        upper.addWidget(instance_state_indicator)
        upper.addWidget(instance_desc)

        upper_container = QFrame()
        upper_container.setProperty("selected", False)
        upper_container.setLayout(upper)

        upper_container.setStyleSheet(f"""
            * {{
                border-radius: 8px;
            }}

            * [selected="false"] {{
                border: 2px solid {self.not_selected_border_color};
            }}
            * [selected="true"] {{
                border: 2px solid {self.selected_border_color};
            }}
        """)

        self.upper_container = upper_container
        self.upper = upper
        self.ins_ix_label = ins_ix_label
        self.instance_state_indicator = instance_state_indicator
        self.instance_desc = instance_desc


    def __has_multiple_cards(self):
        """returns whether this instance has multiple cards attached to it"""
        return 'p4d' in self.instance['instance_type']


    def createBottomLayout(self):
        """This part would contain the connected interfaces"""
        bottom = QHBoxLayout()
        bottom.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.__add_interfaces(bottom)

        bottom_container = QWidget()
        bottom_container.setLayout(bottom)

        # We don't really want to allow to expend
        bottom_container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                       QtWidgets.QSizePolicy.Policy.Fixed)
    
        bottom_container.setStyleSheet("""
            QLabel {
            border-radius: 4px;
            }
        """)

        self.bottom_container = bottom_container
        self.bottom = bottom


    def __add_interfaces(self, hlayout : QHBoxLayout):
        """Add a QLabel widget for each interface of an instance to the given
        @hlayout"""
        for interface in self.instance["interfaces"]:
            # TODO: learn how to do it more professionally
            label = QLabel("      ")
            label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                QtWidgets.QSizePolicy.Policy.Fixed)

            subnet_id = interface['subnet']

            subnet_color = awsh_get_subnet_color(self.region, subnet_id)
            label.setStyleSheet(f'background-color: {subnet_color}')
            if self.__has_multiple_cards():
                label.setText(str(interface['card_id_index']))

            hlayout.addWidget(label)


    def mark(self):
        self.upper_container.setProperty("selected", True)
        self.upper_container.style().polish(self.upper_container)
        self.update()


    def unmark(self):
        self.upper_container.setProperty("selected", False)
        self.upper_container.style().polish(self.upper_container)
        self.update()


    def setIndex(self, index : int):
        self.ins_ix_label.setText(str(index))


    def clearIndex(self):
        self.ins_ix_label.setText("-")
