from PyQt5.QtWidgets import (QWidget, QFrame, QListWidgetItem)
from PyQt5.QtCore import pyqtSignal
from PyQt5.uic import loadUi

# TODO: this has to be changed. Aws class is essential since it keeps (or rather
# will keep) state across invocations. For the GUI however state is not needed
# and creating a class every invocation seems useless and resource wasteful
from awsh_ec2 import Aws, is_instance_running
from awsh_utils import find_in_saved_logins
from awsh_server import awsh_server_commands
from awsh_req_resp_server import awsh_req_client

# TODO: remove all these, they are only here for testing
import threading
import asyncore
import time

import json
import os

AWSH_HOME = os.path.dirname(os.path.realpath(__file__)) + '/..'
print("AWSH_HOME is", AWSH_HOME)

class ec2_instance(QFrame):

    def __init__(self, instance_id, instance, parent = None):

        super().__init__(parent)

        loadUi(AWSH_HOME + "/gui/uis/instance.ui", self)

        self.default_color = "#c9e4c9"
        self.chosen_color  = "#4080bf"

        if is_instance_running(instance):
            instance_ix_str = str(find_in_saved_logins(instance['public_dns']))
        else:
            instance_ix_str = '-'

        self.tag_name.setText(instance["name"])
        self.connection_nr.setText(instance_ix_str)
        self.state.setText(instance["state"]["Name"])
        self.instance_type.setText(instance["instance_type"])
        self.ami_name.setText(instance["ami_name"])

        self.instance_id   = instance_id
        self.instance_object = instance

    def mark(self):
        chosen_backgroud = "background-color: {}".format(self.chosen_color)

        self.setStyleSheet(chosen_backgroud)

    def unmark(self):
        default_backgroud = "background-color: {}".format(self.default_color)
        self.setStyleSheet(default_backgroud)

    def set_instance_index(self, index):
        self.connection_nr.setText(str(index))

class instances_view(QWidget):

    # signals
    widget_update_signal = pyqtSignal(dict)
    action_item_update_signal = pyqtSignal(dict)

    def __init__(self, region, instances = None, parent = None, req_client = None):

        super().__init__(parent)

        loadUi(AWSH_HOME + "/gui/uis/instances_view.ui", self)

        self.row_len = 2
        self.labels = list()
        self.chosen_c = 0
        self.region = region

        self.req_client = req_client

        # Fields added by the ui:
        # instances_layout  = the layout which holds the instances (QGridLayout)
        # region_name       = label that identifies the region (QLabel)
        # action_list       = label list (QListWidget)

        self.region_name.setText(region)
        self.place_widgets(instances)
        self.widget_update_signal.connect(self.update_instances)


        self.action_item_update_signal.connect(self.set_action_item_str)

    def update_instances(self, instances):
        print("gui: Updating widgets for region", self.region)
        # FIXME: a more robust option would be to update the chosen index to
        # point to the same instance it pointed before. Since this index might
        # change, there should be a search by instance id or something
        self.chosen_c = 0
        self.place_widgets(instances)

    # TODO: check if you can use this function with several arguments instead of
    # clamping it into a dictionary. Note that you specified 'dict' in this
    # signal's definition
    def set_action_item_str(self, arguments):
        """This is meant to be invoked as a signal. Arguments is a dictionary
        which should have the attributes @action_item and @string.
        Set the string of the action
        item @action_item to be @string.
        @action_item: a QListWidgetItem item
        @string: the string to set
        """
        action_item = arguments['action_item']
        string      = arguments['action_string']

        action_item.setText(string)

    def add_action(self, action_str):
        """Add an item to the action list"""
        list_item = QListWidgetItem(action_str, self.action_list)
        self.action_list.addItem(list_item)

        return list_item

    def place_widgets(self, instances):

        row_len = self.row_len

        rows_nr = len(instances) / row_len
        glayout = self.instances_layout
        labels = []

        i_nr = 0
        for i_id in instances:
            instance = instances[i_id]

            # create the instance box
            label = ec2_instance(instance_id = i_id,
                                 instance = instance,
                                 parent = self)

            # label.setStyleSheet("background-color:red")

            # add to layout
            glayout.addWidget(label, i_nr // row_len,  i_nr % row_len)

            labels.append(label)

            i_nr = i_nr + 1

        self.labels = labels

        # FIXME: This would break if there were no instances in the region
        self.labels[self.chosen_c].mark()
        glayout.setContentsMargins(15, 15, 15, 15)
        glayout.setSpacing(20)

    def send_client_command(self, command, arguments, handler, action_str):
        try:
            client = awsh_req_client()
            request = '{} {}'.format(command, arguments)
            print('gui, sending request: ' + request)

            action_item_str = "{} - in progress".format(action_str)
            action_item = self.add_action(action_item_str)

            def handle_reply(connection, server_reply):
                connection.close()
                handler(server_reply)

                action_item_str = "{} - done".format(action_str)
                self.action_item_update_signal.emit(
                        {'action_item': action_item, 'action_string': action_item_str}
                        )

            client.send_request(request, handle_reply)
        except:
            print("gui: failed to start connection")
            return
        pass

    def keyPressEvent(self, e):
        if not len(self.labels):
            return

        o_chosen_c = self.labels[self.chosen_c]

        if len(e.text()) == 1 and e.text() in 'hjkl':
            letter = e.text()
            label_len = len(self.labels)
            row_len = self.row_len

            if letter == 'l':
                self.chosen_c = (self.chosen_c + 1) % label_len
            elif letter == 'h':
                self.chosen_c = self.chosen_c - 1
            elif letter == 'j':
                self.chosen_c = (self.chosen_c + row_len) % label_len
            elif letter == 'k':
                self.chosen_c = self.chosen_c - row_len

            if self.chosen_c < 0:
                self.chosen_c += label_len

            n_chosen_c = self.labels[self.chosen_c]

            o_chosen_c.unmark()
            n_chosen_c.mark()
        elif e.text() == 'D':
            print('Calling detach for region {} and instance {}'.format(self.region,
                                                                        o_chosen_c.instance_id))

            ec2 = Aws()
            ec2.detach_private_enis(self.region, o_chosen_c.instance_id)
        elif e.text() == 'I':
            instance = o_chosen_c.instance_object
            # FIXME: Not all instances' username is ec2-user
            username    = 'ec2-user'
            server      = instance['public_dns']
            key         = instance['key']

            print("Adding instance {}@{} with key {} to saved logins".format(
                                                                             username,
                                                                             server,
                                                                             key))

            index = find_in_saved_logins(server = server, username = username,
                                         key = key, add_if_missing = True)
            print("Added at index", str(index))
            o_chosen_c.set_instance_index(index)
            self.add_action("Index {}@{}".format(username, server))
        elif e.text() == 'R': # refresh instances in region
            def update_instance_list(instances_str):
                try:
                    instances = json.loads(instances_str)
                    self.widget_update_signal.emit(instances)
                except:
                    print ("Couldn't transform reply into json. reply:")
                    print(instances_str)
                    return

            self.send_client_command(command=awsh_server_commands.QUERY_REGION,
                arguments=self.region, handler=update_instance_list,
                action_str="Querying region " + self.region)
        elif e.text() == 'S': # start an instance
            instance_id    = o_chosen_c.instance_id

            argument_string="{} {}".format(self.region, instance_id)

            # No need to handle this action anyway special
            def dummy(arg):
                pass

            self.send_client_command(command=awsh_server_commands.START_INSTANCE,
                    arguments=argument_string, handler= dummy,
                action_str="Starting instance " + instance_id)

        elif e.text() == 'F': # start an instance
            instance_id    = o_chosen_c.instance_id

            argument_string="{} {}".format(self.region, instance_id)

            # No need to handle this action anyway special
            def dummy(arg):
                pass

            self.send_client_command(command=awsh_server_commands.STOP_INSTANCE,
                    arguments=argument_string, handler= dummy,
                action_str="Stopping instance " + instance_id)
