from PyQt5.QtWidgets import (QWidget, QListWidgetItem)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.uic import loadUi

from awsh_utils import clean_saved_logins
from awsh_client import awsh_client

from gui.instance import ec2_instance as ec2_instance_v2

import os
import collections

AWSH_HOME = os.path.dirname(os.path.realpath(__file__)) + '/..'

class instances_view(QWidget):

    # signals
    action_item_update_signal = pyqtSignal(dict)
    # TODO: Transform the two upper functions to be handled by the one below
    handle_in_main_thread_signal = pyqtSignal(list)

    def __init__(self, region, region_long_name, instances=dict(),
                 interfaces=dict()):

        super().__init__()

        loadUi(AWSH_HOME + "/gui/uis/instances_view.ui", self)

        # subnet used colors dictionary
        self.subnet_color_dict = dict()

        self.row_len = 2
        self.labels = list()
        self.chosen_instance_item = 0
        self.region = region

        self.lowest_instance_ix = 99

        # Fields added by the ui:
        # instances_layout  = the layout which holds the instances (QGridLayout)
        # region_name       = label that identifies the region (QLabel)
        # action_list       = label list (QListWidget)

        self.action_item_update_signal.connect(self.complete_action_item)
        self.handle_in_main_thread_signal.connect(self.handle_in_main_thread)

        self.pending_actions = dict()
        self.client = awsh_client(region=region, instances=instances,
                                  interfaces=interfaces,
                                  subnet_color_dict=self.subnet_color_dict)

        region_str = f'{region_long_name} | {region}'
        self.region_name.setText(region_str)
        self.place_widgets(instances)

    def handle_in_main_thread(self, action: list):
        """A generic signal handler which executes a function with its
        arguments in QT main thread (usually things that require GUI change).
        @action - a list with two items:
                  [0] - the handler to executes
                  [1] - the arguments to pass to the handler (dictionary)"""
        handler = action[0]
        arguments = action[1]

        print("called to update in main thread")

        handler(arguments)

    def update_instances(self, instances: dict):
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
    def complete_action_item(self, arguments: dict):
        """This is meant to be invoked as a signal. Arguments is a dictionary
        which should have the attributes @action_item and @string.
        Set the string of the action
        item @action_item to be @string.
        @action_item: a QListWidgetItem item
        @string: the string to set
        """
        action_item = arguments['action_item']
        string = arguments['action_string']

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

        def handle_request_completion(request_id, response_success, server_reply=None):

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

        glayout = self.instances_layout

        glayout.setAlignment(Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignTop)
    
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
            # label = ec2_instance(instance_id=i_id,
                                 # instance=instance,
                                 # subnet_color_dict=self.subnet_color_dict,
                                 # parent=self)
            label = ec2_instance_v2(
                instance=instance,
                region=self.region)

            # self.lowest_instance_ix = min(self.lowest_instance_ix,
                                          # label.get_instance_index())
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

            instance = old_chosen_instance_item.instance_object

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

            # return to default value
            self.lowest_instance_ix = 99
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

        elif e.text() == 'F': # stop an instance
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
            self.pending_actions[request_id] = {'action_item': action_item, 'action_string': action_string}
        elif e.text() == 'T':
            instance = old_chosen_instance_item.instance_object
            instance_id = instance['id']
            region = self.region

            target_launch_str = f'aws ec2 start-instances --region {region} --instance-ids {instance_id} --additional-info "target-droplet="'
            print(target_launch_str)
            os.system(f"echo -n '{target_launch_str}' | xclip -selection clipboard")
        elif e.text() == 'A':
            instance = old_chosen_instance_item.instance_object
            instance_id = instance['id']
            region = self.region

            import json
            script_path = os.path.dirname(os.path.abspath(__file__))
            # TODO: dirty hack. You don't need to have this code here anyway but
            # rather in a private file. Also the layout shouldn't be assumed in
            # a way like this
            script_path += "/../ec2_az.json"
            with open(script_path, "r") as jsfile:
                az_data = json.load(jsfile)

            admiral_link = f'https://admiral-{az_data[region]}.ec2.amazon.com/search?q={instance_id}'
            print(admiral_link)
            os.system(f"echo -n '{admiral_link}' | xclip -selection clipboard")
