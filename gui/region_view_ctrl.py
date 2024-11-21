from typing import Dict, Tuple, Union, Callable, Any
import logging

from awsh_client import awsh_client

from PyQt5.QtCore import QObject, pyqtSignal

from awsh_ui import awsh_ui
from awsh_utils import awsh_get_subnet_color, clean_saved_logins, find_in_saved_logins, get_available_interface_in_az_list, get_login_and_kernel_by_ami_name


class region_view_command_status(QObject):
    COMMAND_STATUS_INITIATED = 0
    COMMAND_STATUS_FAILED = 1
    COMMAND_STATUS_UPDATE = 2
    COMMAND_STATUS_SUCCESS = 3


class region_view_signals(QObject):
    instance_selection_changed = pyqtSignal()
    keybinding_changed = pyqtSignal()
    server_commands_added = pyqtSignal()
    instances_list_changed = pyqtSignal()
    instances_indices_changed = pyqtSignal()


CLIENT_FUNC_TYPE = Callable[[Callable], Any]
CLIENT_CB_TYPE = Callable[[Any, Union[dict, None]], None]


class region_view_ctl():
    """This is the handling class of all region_view class events. This class
    could be considered the model of the view"""

    def __init__(self, region : str, instances : list,
                 interfaces : dict, subnets : dict,
                 inst_row_len : int, signals : region_view_signals) -> None:

        self.logger = logging.getLogger(f"awsh_region_view_ctl_{region}")
        # TODO: this doesn't work for some reason... Only 'INFO' logs show
        self.logger.setLevel('DEBUG')

        self.region = region
        self.instances = instances
        self.interfaces = interfaces
        self.subnets = subnets
        self.signals = signals
        self.instances_row_len = inst_row_len
        # this can later be set to an awsh_ui derived class
        # which allows to receive input from the user
        self.ui = None

        self.chosen_instance_ix = 0
        self.previous_selected_instance = None
        self.keybindings_menu_stack = list()
        # the commands we send to the server
        self.server_commands = list()
        self.instances_indices = None

        self.client = awsh_client(region, instances, interfaces)

        self._configureKeybindings()


    def setUI(self, ui_class : awsh_ui):
        self.ui = ui_class


    def getSelectedInstance(self) -> Union[int, None]:
        """ returns the instance which needs to be marked"""
        if not len(self.instances):
            return None

        return self.chosen_instance_ix


    def getPreviouslySelectedInstance(self) -> Union[int, None]:
        """ returns the instance which was previously selected and now need to
        be unmarked"""
        return self.previous_selected_instance


    def _getInstancesCachedIndices(self):
        instances_indices = dict()
        for i, instance in enumerate(self.instances):
            address = instance['public_dns']
            index = find_in_saved_logins(address)
            if index is not None:
                instances_indices[i] = index

        self.instances_indices = instances_indices


    def getInstancesIndices(self) -> Dict:
        """Returns a dictionary whose keys are instances indices and
        values are their cached indices. If an instance index is not there then
        it has no index"""
        self._getInstancesCachedIndices()

        return self.instances_indices


    def getInstancesList(self) -> list:
        """Get dictionary representing the instances"""
        return self.instances


    def getSubmittedCommands(self):
        """Return an array of commands sent to the server.
        each element in the list is a dictionary which has the
        fields
        @desc: String describing the action
        @status: what stage the command is in now
        @server_update_str: last update from server"""
        return self.server_commands


    # wrapper around commands sent to the server
    def __runCommandInServer(self, client_func : CLIENT_FUNC_TYPE, cb : CLIENT_CB_TYPE, command_str : str):

        action = {
            "desc" : command_str,
            "status" : region_view_command_status.COMMAND_STATUS_INITIATED,
            "server_update_str" : "",
        }
        self.server_commands.append(action)

        self.signals.server_commands_added.emit()

        # TODO: remove this req_id argument. It belongs to client and shouldn't
        # be exposed
        # TODO: it makes no sense to pass around server dict. Client should
        # update its own data structures. Otherwise it's messy
        def client_cb(req_id : int, status : int, server_reply : dict):
            self.logger.info("Server command finished with status {}".format(
                              status))

            if status != 0:
                action["status"] = region_view_command_status.COMMAND_STATUS_FAILED
                self.signals.server_commands_added.emit()
                cb(False, None)
                return

            # TODO: add support for other status (like update for example)
            action["status"] = region_view_command_status.COMMAND_STATUS_SUCCESS
            self.signals.server_commands_added.emit()

            cb(True, server_reply)

        client_func(client_cb)


    def _refreshInstances(self):
        client = self.client

        self.logger.info("Refreshing instances")

        # TODO: for now we discard server's reply because we trust the client to
        # update instances list, but that approach is wrong. We should remove
        # any state from the client
        def __refresh_instances_cb(success : Any, _):
            if not success:
                return

            # make sure selection is still valid
            # some instances might be terminated and the new insatnces
            # list is different
            prev_select_instance = self.instances[self.chosen_instance_ix]
            prev_instance_id = prev_select_instance["id"]

            chosen_ix = None
            for ix, instance in enumerate(client.instances):
                if instance["id"] == prev_instance_id:
                    chosen_ix = ix
                    break

            # selected instance no longer exists
            instances_nr = len(client.instances)
            if chosen_ix is None and instances_nr > 0:
                # this would cover both None case and 0
                if not self.chosen_instance_ix:
                    chosen_ix = 0   
                else:
                    chosen_ix = (self.chosen_instance_ix - 1) % instances_nr


            self.logger.info("region instances queried. Emitting signal")

            self.chosen_instance_ix = chosen_ix
            # TODO: need to decide whether the client should hold any state. It
            # is really only needed to know which ENIs I can still attach and
            # which not
            self.instances = client.instances
            self.signals.instances_list_changed.emit()


        self.__runCommandInServer(lambda cb : client.refresh_instances(cb),
                                     __refresh_instances_cb,
                                     f"Querying instances in {self.region}")


    def __chooseENIToConnect(self) -> Tuple[Any, Union[str, None], Union[str, None]]:
        """Connect an ENI to an insterface. The user is allowed to choose to
        create a new interface or a new subnet altogether"""

        if self.chosen_instance_ix is None:
            return None, None, None

        if self.ui is None:
            raise Exception("Request to connect ENI but no UI was set")

        instance = self.instances[self.chosen_instance_ix]
        instance_az = instance["az"]

        available_enis = get_available_interface_in_az_list(
            self.interfaces,
            self.instances,
            instance_az)

        subnets = self.subnets.values()
        available_subnets_ids = list()
        for subnet in subnets:
            if subnet["az"] == instance_az:
                available_subnets_ids.append(subnet["id"])

        # now we construct the choices list
        interfaces_choices = list()
        for eni in available_enis:
            interface : dict = self.interfaces[eni]
            interface_subnet_id = interface["subnet"]


            name = interface["name"] if interface["name"] else interface["id"]
            subnet_color = awsh_get_subnet_color(self.region, interface_subnet_id)
            interface_option = {
                "entry" : name,
                "color" : subnet_color
            }
            interfaces_choices.append(interface_option)
        
        # construct subnets list (in case user wants to create new ENIs)
        subnets_choices = list()
        for subnet_id in available_subnets_ids:
            subnet = self.subnets[subnet_id]

            subnet_color = awsh_get_subnet_color(self.region, subnet_id)
            subnet_option = {
                "entry" : subnet["id"],
                "color" : subnet_color
            }
            subnets_choices.append(subnet_option)
        
        # add an option to create new ENIs
        interfaces_choices.append({
                                      "entry" : "create new ENIs",
                                      "submenu" : (
                                          "Choose subnet to create interfaces in:",
                                          subnets_choices
                                      )
                                  })

        # add an option to create a new subnet
        subnets_choices.append("Create new subnet")

        success, choices = self.ui.multiline_selection("which ENI to connect?", interfaces_choices)
        if not success:
            return None, None, None

        eni_choice = choices[0]
        chosen_eni = available_enis[eni_choice] if eni_choice < len(available_enis) else None

        chosen_subnet = None
        # user requested to create interaces (maybe a subnet as well)
        if len(choices) > 1:
            subnet_choice = choices[1]
            print("Have " + str(len(subnets_choices)) + " choices and choice is " + str(subnet_choice))
            if subnet_choice < (len(subnets_choices) - 1):
                chosen_subnet = subnets_choices[subnet_choice] 

        return True, chosen_eni, chosen_subnet


    def __conectExistigENI(self, eni_id: str):
        """Connect an ENI to the current instnace"""

        instance : dict = self.instances[self.chosen_instance_ix]
        instance_id = instance["id"]
        eni = self.interfaces[eni_id]

        # mark the eni as currently in use
        eni["status"] = 'connecting'
        num_interface = instance['num_interfaces']
        instance["num_interfaces"] = num_interface + 1

        def __connectExistingEniCB(success : Any, server_reply : Union[dict, None]):
            if not success:
                eni["status"] = 'available'
                return

            instance_info = server_reply
            if instance_info is not None:
                instance.update(instance_info)

            eni["status"] = 'in-use'
            # while it's not true, it's easier than asking the GUI to draw a
            # specific instance
            self.signals.instances_list_changed.emit()
    
        client = self.client
        instance_name = instance["id"]
        if instance["name"]:
            instance_name = instance_name + f" ({instance['name']})"

        notification_str = f"Attaching {eni_id} to {instance_name} at index {num_interface}"
        self.__runCommandInServer(lambda cb : client.connect_eni(instance_id,
                                                                 eni_id,
                                                                 num_interface,
                                                                 cb),
                                  __connectExistingEniCB,
                                  notification_str)


    def __createSubnet(self):
        """Request the client (and server in turn) to create a new subnet and
        two enis for it"""
        # This function assumes chosen_instance_ix is valid
        instance = self.instances[self.chosen_instance_ix]
        instance_az = instance["az"]

        def __createSubnetCB(success : Any, server_reply : Union[dict, None]):
            if not success:
                return

            if server_reply is not None:
                self.interfaces.update(server_reply.get('interfaces', dict()))
                self.subnets.update(server_reply.get('subnets', dict()))


        client = self.client
        notification_str = f"Creating an interface and two ENIs in availability zone {instance_az}"
        self.__runCommandInServer(lambda cb : client.create_subnet(instance_az, cb),
                                  __createSubnetCB,
                                  notification_str)

    def _connetENIToInstance(self):
        """Query user about an ENI to attach. The user can also choose to create
        new interfaces or a new subnet instead"""
        success, eni_id, subnet_id = self.__chooseENIToConnect()
        if not success:
            return

        # user chose an existing ENI
        if eni_id:
            self.__conectExistigENI(eni_id)
            return

        if subnet_id:
            print("Creating interfaces in an existing subnet is not supported yet")
            return

        print("Creating a new subnet")
        self.__createSubnet()


    def _detachAllEnis(self):
        if self.chosen_instance_ix is None:
            return

        instance : dict = self.instances[self.chosen_instance_ix]
        instance_id = instance["id"]

        def __detachAllENIsCB(success : Any, server_reply : Union[dict, None]):
            if not success or server_reply is None:
                return

            detached_enis = server_reply["detached_enis"]
            instance_info = server_reply["instance"]

            for eni_id in detached_enis:
                if eni_id in self.interfaces:
                    self.interfaces[eni_id]["status"] = "available"

            instance.update(instance_info)
            # while it's not true, it's easier than asking the GUI to draw a
            # specific instance
            self.signals.instances_list_changed.emit()

        client = self.client

        instance_name = instance["id"]
        if instance["name"]:
            instance_name = instance_name + f" ({instance['name']})"

        notification_str = f"Detaching all secondary enis from {instance_name}"
        self.__runCommandInServer(lambda cb : client.detach_all_enis(instance_id, cb),
                                  __detachAllENIsCB,
                                  notification_str)


    def _setCurrentInstanceState(self, state : int):
        """Modify the current instance state
        state: one of fallowing values
            0: start instance
            1: shutdown instance
            2: reboot instance
            3: terminate instance"""

        print("Setting instance state", state)
        # TODO: maybe give a user a message about it?
        # Seems kinda obvious that an instance needs to chosen
        # Since there are quite a few instance related functions maybe add a
        # decorator around it
        if self.chosen_instance_ix is None:
            return

        # Currently the other two aren't implemented
        if state >= 2:
            return

        client = self.client
        instance = self.instances[self.chosen_instance_ix]

        def __set_state_func(cb):
            self.client.set_instance_state(instance, state, cb)   


        def __set_state_cb(success : Any, _):
            if not success:
                return

            self.instances = client.instances
            self.signals.instances_list_changed.emit()

        action_strs = [ 
            "Starting", "Stopping", "Rebooting", "Terminating"
        ]

        action = action_strs[state]
        instance_id = instance["id"]
        label = f"{action} instance {instance_id}"

        self.__runCommandInServer(__set_state_func, __set_state_cb, label)


    def _addKeybindingSubmenu(self, kb_menu : dict, kb_submenu : dict, desc :
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

        self._addKeybind(kb_submenu, "cancel", "c", [], go_prev_kb_menu)


    def getCurrentKbMenu(self) -> dict:
        """Return current keybindings"""
        return self.keybindings_menu_stack[-1]


    def _addKeybind(self, kb_menu : dict, desc : str, key : str, aliases : list, func):
        def executeFuncAndReturnToRootMenu():
            func()

            # return to root menu if we've moved to a submenu
            keybinding_stack = self.keybindings_menu_stack
            if len(keybinding_stack) == 1:
                return

            self.keybindings_menu_stack = keybinding_stack[:1]

            self.signals.keybinding_changed.emit()
            
        kb_menu[key] = {
            "desc" : desc,
            "func" : executeFuncAndReturnToRootMenu,
        }

        for a in aliases:
            kb_menu[a] = kb_menu[key]


    def __changedSelectedInstance(self, amount):
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


    def _index_current_instance(self):
        if self.chosen_instance_ix is None:
            return

        instance = self.instances[self.chosen_instance_ix]

        server = instance["public_dns"]
        login, kernel = get_login_and_kernel_by_ami_name(instance["ami_name"])

        print("caching instance", server)
        index = find_in_saved_logins(server,
                                     username=login,
                                     key=instance["key"],
                                     kernel=kernel,
                                     add_if_missing=True)
        if index is None:
            return

        self.instances_indices[self.chosen_instance_ix] = index # pyright: ignore
        self.signals.instances_indices_changed.emit()


    def _clear_all_indices(self):
        clean_saved_logins()
        self.instances_indices = dict()
        self.signals.instances_indices_changed.emit()


    def _configureKeybindings(self):
        root_kb = dict()

        # instance selection movement
        rl = self.instances_row_len
        for keys, amount in \
            [ ["h", -1] , ["j", rl], ["k", -rl], ["l", 1] ]:
            func = lambda a=amount:  self.__changedSelectedInstance(a)
            self._addKeybind(root_kb, "", keys, [], func)

        # Instances submenu
        instances_menu = dict()
        self._addKeybind(instances_menu, "refresh", "r", [], self._refreshInstances)
        # add state keybindings
        state_tuples = [ ("start", "s", 0), ("Stop", "S", 1),
                            ("Reboot", "R", 2), ("terminate", "t", 3)]
        for string, key, state in state_tuples:
            self._addKeybind(instances_menu,
                              string, key, [],
                              lambda s = state :
                                  self._setCurrentInstanceState(s))

        self._addKeybindingSubmenu(root_kb, instances_menu, "instances", "i")

        # Interfaces submenu
        interfaces_manu = dict()
        self._addKeybind(interfaces_manu, "attach", "a", [],
                         self._connetENIToInstance)
        self._addKeybind(interfaces_manu, "Detach all enis", "D", [],
                         self._detachAllEnis)

        self._addKeybindingSubmenu(root_kb, interfaces_manu, "enis", "e")

        indices_manu = dict()
        self._addKeybind(indices_manu, "Index instance", "I", [],
                         self._index_current_instance)
        self._addKeybind(indices_manu, "Clear cached instances", "C", [],
                         self._clear_all_indices)

        self._addKeybindingSubmenu(root_kb, indices_manu, "Indices", "I")

        self.keybindings_menu_stack.append(root_kb)


    def keyPressedEvent(self, e):
        letter = e.text()

        kb_menu = self.keybindings_menu_stack[-1]

        if letter not in kb_menu:
            return False

        kb = kb_menu[letter]
        func = kb["func"]

        func()

        # handled
        return True
