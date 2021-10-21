from PyQt5.QtWidgets import (QWidget, QFrame, QListWidgetItem, QLabel, QGridLayout)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.uic import loadUi

from awsh_ec2 import is_instance_running
from awsh_utils import find_in_saved_logins, clean_saved_logins
from awsh_client import awsh_client

import json
import os
import collections

AWSH_HOME = os.path.dirname(os.path.realpath(__file__)) + '/..'

# SUBNET_COLORS = ['#fff3d0', '#e7d0ff', '#2f5a9dff', '#912f9dff', '#9d2f2fff', '#6e6a12ff', '#c00909ff']
def rgb(red, green, blue):
    return '#%02x%02x%02x' % (red, green, blue)

# SUBNET_COLORS = [rgb(27, 1, 29), rgb(36, 3, 55), rgb(39, 4, 79), rgb(38, 5, 105), rgb(31, 6, 133), rgb(25, 8, 158), rgb(8, 21, 175), rgb(8, 46, 165),
        # rgb(7, 64, 147), rgb(6, 78, 131), rgb(6, 90, 118), rgb(5, 101, 109), rgb(5, 112, 100), rgb(6, 122, 89), rgb(6, 132, 75), rgb(7, 142, 57),
        # rgb(7, 152, 37), rgb(8, 162, 15), rgb(20, 172, 8), rgb(43, 181, 9), rgb(74, 188, 9), rgb(107, 195, 9), rgb(142, 200, 10), rgb(177, 203, 10),
        # rgb(212, 205, 10), rgb(247, 205, 83), rgb(251, 211, 169), rgb(252, 221, 203), rgb(254, 232, 224), rgb(254, 244, 240)]
SUBNET_COLORS = ['#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',] 

# SUBNET_COLORS = ['#ff0000','#ff4f00','#ff9f00','#ffee00','#c1ff00','#72ff00','#22ff00','#00ff2d','#00ff7c','#00ffcb','#00e3ff','#0094ff','#0045ff','#0a00ff','#5a00ff','#a900ff','#f700fe',
    # '#ff00b6','#ff0067','#ff0018']

class ec2_instance(QFrame):

    def __init__(self, instance_id, instance, subnet_color_dict, parent = None):

        super().__init__(parent)

        loadUi(AWSH_HOME + "/gui/uis/instance.ui", self)

        self.default_color = "#c9e4c9"
        self.chosen_color  = "#4080bf"

        if is_instance_running(instance):
            instance_ix_str = str(find_in_saved_logins(instance['public_dns']))
        else:
            instance_ix_str = '-'

        tag_name = instance["name"] if instance["name"] != "" else instance["id"]
        self.tag_name.setText(tag_name)
        self.connection_nr.setText(instance_ix_str)
        self.instance_type.setText(instance["instance_type"])

        # This property affects how the color of the instance object
        # We currently only allow to states
        instance_state = "running" if instance["state"]["Name"] == "running" else "stopped"
        self.setProperty("instance_state", instance_state)

        # Don't show the selection asterix at first
        self.sel_img.setHidden(True)

        self.instance_id   = instance_id
        self.instance_object = instance

        self.subnet_color_dict = subnet_color_dict

        # TODO: Move it to the server side. The client doesn't need these values
        # unordered anyway
        def interface_devide_ix(interface):
            return interface["device_index"]

        # soft the interfaces by their device index
        instance["interfaces"].sort(key=interface_devide_ix)
        self.add_interfaces(instance)

    def __has_multiple_cards(self):
        """returns whether this instance has multiple cards attached to it"""
        return 'p4d' in self.instance_object['instance_type']

    def add_interfaces(self, instance):
        self.interfaces_layout.setAlignment(Qt.AlignLeft)

        subnet_color_dict = self.subnet_color_dict

        interfaces_labels = list()
        for interface in instance["interfaces"]:
            description = interface['description']
            # label = QLabel(description)
            label = QLabel()
            self.interfaces_layout.addWidget(label)

            subnet_id = interface['subnet']
            if not subnet_id in subnet_color_dict:
                new_color = SUBNET_COLORS[ len(subnet_color_dict) % len(SUBNET_COLORS) ]
                subnet_color_dict[subnet_id] = new_color

            subnet_color = subnet_color_dict[subnet_id]

            label.setStyleSheet(f'background-color: {subnet_color}')

            # set card index (only for cards with multiple cards)
            if self.__has_multiple_cards():
                label.setText(str(interface['card_id_index']))

            interfaces_labels.append(label)

    def mark(self):
        self.sel_img.setHidden(False)
        # self.setProperty("chosen", True)
        # self.style().polish(self)
        # self.update()
        pass

    def unmark(self):
        self.sel_img.setHidden(True)
        # self.setProperty("chosen", False)
        # self.style().polish(self)
        # self.update()
        pass

    def set_instance_index(self, index):
        self.connection_nr.setText(str(index))

class instances_view(QWidget):

    # signals
    action_item_update_signal = pyqtSignal(dict)
    # TODO: Transform the two upper functions to be handled by the one below
    handle_in_main_thread_signal = pyqtSignal(list)

    def __init__(self, region, region_long_name, instances=dict(), interfaces=dict(), parent=None):

        super().__init__(parent)

        loadUi(AWSH_HOME + "/gui/uis/instances_view.ui", self)

        # subnet used colors dictionary
        self.subnet_color_dict = dict()

        self.row_len = 2
        self.labels = list()
        self.chosen_instance_item = 0
        self.region = region

        # Fields added by the ui:
        # instances_layout  = the layout which holds the instances (QGridLayout)
        # region_name       = label that identifies the region (QLabel)
        # action_list       = label list (QListWidget)

        self.action_item_update_signal.connect(self.complete_action_item)
        self.handle_in_main_thread_signal.connect(self.handle_in_main_thread)

        self.pending_actions = dict()
        self.client = awsh_client(region=region, instances=instances, interfaces=interfaces, subnet_color_dict=self.subnet_color_dict)

        region_str = f'{region_long_name} | {region}'
        self.region_name.setText(region_str)
        self.place_widgets(instances)

    def handle_in_main_thread(self, action : list):
        """A generic signal handler which executes a function with its
        arguments in QT main thread (usually things that require GUI change).
        @action - a list with two items:
                  [0] - the handler to executes
                  [1] - the arguments to pass to the handler (dictionary)"""
        handler = action[0]
        arguments = action[1]

        print("called to update in main thread")

        handler(arguments)

    def update_instances(self, instances : dict):
        print("gui: Updating widgets for region", self.region)

        chosen_item_ix = 0
        labels_len = len(self.labels)
        if labels_len:
            previous_chosen_instance_id = self.labels[self.chosen_instance_item].instance_id
            print("previous_chosen_instance_id is {}".format(previous_chosen_instance_id))
            # This assumes that the iteration over dictionaries keys is
            # deterministic since place_widgets() would iterate over this
            # dictionary as well. TODO: check this assumption
            for instance_id in instances:
                if instance_id == previous_chosen_instance_id:
                    break
                chosen_item_ix = chosen_item_ix + 1

            chosen_item_ix = 0 if chosen_item_ix == len(instances) else chosen_item_ix

        self.chosen_instance_item = chosen_item_ix

        self.place_widgets(instances)

    # TODO: check if you can use this function with several arguments instead of
    # clamping it into a dictionary. Note that you specified 'dict' in this
    # signal's definition
    def complete_action_item(self, arguments : dict):
        """This is meant to be invoked as a signal. Arguments is a dictionary
        which should have the attributes @action_item and @string.
        Set the string of the action
        item @action_item to be @string.
        @action_item: a QListWidgetItem item
        @string: the string to set
        """
        action_item     = arguments['action_item']
        string          = arguments['action_string']

        # TODO: add coloring to the string
        if 'error_string' in arguments:
            string = string + " - Failed ({})".format(arguments['error_string'])
        else:
            string = string + " - Done"

        action_item.setText(string)

    def add_action(self, action_str):
        """Add an item to the action list"""
        action_str = action_str + " - in progress"
        list_item = QListWidgetItem(action_str, self.action_list)
        self.action_list.addItem(list_item)

        return list_item
    
    def handle_complation(self, reply_handler = None):
        """Create a custom completion handler. This returns a function that can
        be passed to awsh_client class. This function is called with the request
        id and server's reply"""

        def handle_request_completion(request_id, response_success, server_reply = None):

            print(f"Received request completion for request id {request_id}")
            # If we failed the request, don't call reply handler
            if not reply_handler is None and response_success:
                # this transformation is needed. Otherwise the signal messes the
                # order of the reply (at least when it's a dictionary)
                server_reply = collections.OrderedDict(server_reply)
                self.handle_in_main_thread_signal.emit([reply_handler, server_reply])

            if not response_success:
                self.pending_actions[request_id]['error_string'] = f'server error: {server_reply}'

            print("updating action string")
            self.action_item_update_signal.emit(self.pending_actions[request_id])

        return handle_request_completion

    def place_widgets(self, instances):

        row_len = self.row_len

        rows_nr = len(instances) / row_len

        glayout = self.instances_layout
        # remove all existing widgets from layout. This ensures that instances
        # that no longer exist don't linger in the gui version
        while glayout.count():
            item = glayout.takeAt(0)
            instance = item.widget()
            if instance is not None:
                instance.deleteLater()

        labels = []

        i_nr = 0
        for i_id in instances:
            instance = instances[i_id]

            # create the instance box
            label = ec2_instance(instance_id = i_id,
                                 instance = instance,
                                 subnet_color_dict = self.subnet_color_dict,
                                 parent = self)

            # add to layout
            glayout.addWidget(label, i_nr // row_len,  i_nr % row_len)

            labels.append(label)

            i_nr = i_nr + 1

        self.labels = labels

        if len(labels) > 0:
            self.labels[self.chosen_instance_item].mark()

        glayout.setContentsMargins(15, 15, 15, 15)
        glayout.setSpacing(20)

    def keyPressEvent(self, e):
        if not len(self.labels):
            return

        old_chosen_instance_item = self.labels[self.chosen_instance_item]

        if len(e.text()) == 1 and e.text() in 'hjkl':
            letter = e.text()
            label_len = len(self.labels)
            row_len = self.row_len

            if letter == 'l':
                self.chosen_instance_item = (self.chosen_instance_item + 1) % label_len
            elif letter == 'h':
                self.chosen_instance_item = self.chosen_instance_item - 1
            elif letter == 'j':
                self.chosen_instance_item = (self.chosen_instance_item + row_len) % label_len
            elif letter == 'k':
                self.chosen_instance_item = self.chosen_instance_item - row_len

            if self.chosen_instance_item < 0:
                self.chosen_instance_item += label_len

            n_chosen_instance_item = self.labels[self.chosen_instance_item]

            old_chosen_instance_item.unmark()
            n_chosen_instance_item.mark()
        elif e.text() == 'D':
            print('Calling detach for region {} and instance {}'.format(self.region,
                                                                        old_chosen_instance_item.instance_id))

            instance    = old_chosen_instance_item.instance_object

            callback = self.handle_complation()
            request_id = self.client.detach_all_enis(instance, finish_callback=callback)
            if request_id is None:
                return

            inst_name   = instance['name']
            inst_id     = instance['id']
            # TODO: you can define instance 'to_string' function so that it will
            # do this formatting itself
            action_string = "Detaching ENIs from " + (f"{inst_name} ({inst_id})" if inst_name else f"{inst_id}")
            action_item = self.add_action(action_string)
            self.pending_actions[request_id] = { 'action_item': action_item, 'action_string' : action_string }

        elif e.text() == 'I':
            instance = old_chosen_instance_item.instance_object

            handler = old_chosen_instance_item.set_instance_index
            index = self.client.index_instance(instance, finish_callback = handler)

            inst_name   = instance['name']
            inst_id     = instance['id']

            action_string = "Indexing instance " + (f"{inst_name} ({inst_id})" if inst_name else f"{inst_id}")
            action_item = self.add_action(action_string)

            self.complete_action_item({ 'action_item': action_item, 'action_string' : action_string })
        elif e.text() == 'C':
            action_string = "Cleaning saved_logins".format(self.region)
            action_item = self.add_action(action_string)

            clean_saved_logins()

            for instance in self.labels:
                instance.set_instance_index('-')

            self.complete_action_item({ 'action_item': action_item, 'action_string' : action_string })

        elif e.text() == 'R': # refresh instances in region
            callback = self.handle_complation(self.update_instances)
            request_id = self.client.refresh_instances(finish_callback=callback)
            if request_id is None:
                return

            action_string = "Querying region {}".format(self.region)
            action_item = self.add_action(action_string)
            self.pending_actions[request_id] = { 'action_item': action_item, 'action_string' : action_string }

        elif e.text() == 'S': # start an instance
            instance    = old_chosen_instance_item.instance_object

            callback = self.handle_complation(self.update_instances)
            request_id = self.client.start_instance(instance, finish_callback=callback)
            if request_id is None:
                return

            inst_name   = instance['name']
            inst_id     = instance['id']

            action_string = "Starting instance " + (f"{inst_name} ({inst_id})" if inst_name else f"{inst_id}")
            action_item = self.add_action(action_string)
            self.pending_actions[request_id] = { 'action_item': action_item, 'action_string' : action_string }

        elif e.text() == 'F': # start an instance
            instance    = old_chosen_instance_item.instance_object

            request_id = self.client.stop_instance(instance, finish_callback=self.handle_complation())
            if request_id is None:
                return

            inst_name   = instance['name']
            inst_id     = instance['id']

            action_string = "Stopping instance " + (f"{inst_name} ({inst_id})" if inst_name else f"{inst_id}")
            action_item = self.add_action(action_string)
            self.pending_actions[request_id] = { 'action_item': action_item, 'action_string' : action_string }

        elif e.text() == 'c':
            instance    = old_chosen_instance_item.instance_object

            client = self.client
            request_id, interface = client.connect_eni(instance, finish_callback=self.handle_complation())

            # the operation has been canceled
            if request_id is None:
                return

            if interface:
                inf_name = interface['name']
                inf_id = interface['id']
                action_string = "Connecting ENI " + (f"{inf_name} ({inf_id})" if inf_name else f"{inf_id}")
            else:
                action_string = "Creating 2 ENIs"

            action_item = self.add_action(action_string)
            self.pending_actions[request_id] = { 'action_item': action_item, 'action_string' : action_string }
        elif e.text() == 'T':
            instance    = old_chosen_instance_item.instance_object
            instance_id = instance['id']
            region      = self.region
            
            target_launch_str=f'aws ec2 start-instances --region {region} --instance-ids {instance_id} --additional-info "target-droplet="'
            print(target_launch_str)
            os.system(f"echo -n '{target_launch_str}' | xclip -selection clipboard")
