from awsh_req_resp_server import awsh_req_client
from awsh_server import awsh_server_commands
from awsh_utils import find_in_saved_logins, clean_saved_logins

import json
from rofi import Rofi
import re

# TODO: unify it to a single interface
SUBNET_COLORS = ['#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',]

def get_current_state():
 
    # from awsh_cache import awsh_cache

    # cache = awsh_cache()
    # if not cache.read_cache():
        # print("Failed to read cache")
    # return cache.get_instances()

    req_client = awsh_req_client(fail_if_no_server=True, synchronous=True)
    command = awsh_server_commands.GET_CURRENT_STATE
    request = '{}'.format(command)

    # import pickle

    # return pickle.loads(req_client.send_request_blocking(request))
    return json.loads(req_client.send_request_blocking(request))

class awsh_client:
    """This class is the counterpart of awsh_server. Its purpose is to send
    requests to it and process its reply. It shouldn't be used without a running
    server"""

    def __init__(self, region, instances, interfaces, subnet_color_dict):
        # state variable. Holds current regions state
        self.region     = region
        self.instances  = instances
        self.interfaces = interfaces
        self.subnet_color_dict = subnet_color_dict

        self.remove_used_interfaces_from_pool()

        self.next_req_id = 0
        pass


    def remove_used_interfaces_from_pool(self):
        """Mark interfaces which are attached to interfaces as used. This way
        they won't be presented as an option when connecting an interface"""

        for instance in self.instances.values():
            for interface in instance['interfaces']:
                eni = interface['id']
                # default interfaces not always listed in interfaces or the data
                # might be stale
                if eni in self.interfaces:
                    self.interfaces[eni]['status'] = "in-use"


    def send_client_command(self, command, arguments, request_id, handler = None):
        try:
            req_client = awsh_req_client()
            request = '{} {}'.format(command, arguments)

            # this function is called by the request client
            # after it finishes its connection with the server
            def handle_reply(connection, response_success, server_reply):
                connection.close()
                if handler is None:
                    return

                # If we failed the request, the reply is the string of the
                # exception
                if not response_success:
                    print(f"request id {request_id} failed with status {response_success} and reply {server_reply}")
                    handler(request_id = request_id, response_success = response_success, server_reply = server_reply)
                    return

                # replies for success are dictionaries
                try:
                    if server_reply != "":
                        reply = json.loads(server_reply)
                    else:
                        reply = dict()

                    handler(request_id = request_id, response_success = response_success, server_reply = reply)
                except:
                    # TODO: Check that it's actually a json error. This is
                    # just ridicules that you fail for any exception
                    print ("Couldn't transform reply into json. reply:")
                    print(server_reply)

            req_client.send_request(request, handle_reply)
        except Exception as exc:
            print("aws_client: failed to start connection")
            raise exc
            return
        pass


    def start_instance(self, instance, finish_callback = None):
        instance_id = instance['id']

        # TODO: this cannot really be integrated because 'finish_callback'
        # receives argument which you don't pass. Also the self.instances struct
        # isn't updated across invocations
        def update_interface_state(finish_callback):
            """Update the available interface lists"""
            if finish_callback is not None:
                finish_callback()
            for eni, interface in self.interfaces.items():
                self.interfaces[eni]['status'] = "available"

            self.remove_used_interfaces_from_pool()

        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        # Send command to server
        argument_string="{} {}".format(self.region, instance_id)
        self.send_client_command(command=awsh_server_commands.START_INSTANCE,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id


    def stop_instance(self, instance, finish_callback = None):
        instance_id = instance['id']

        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        # Send command to server
        argument_string="{} {}".format(self.region, instance_id)
        self.send_client_command(command=awsh_server_commands.STOP_INSTANCE,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id


    def refresh_instances(self, finish_callback=None):
        """Send the server a request to query all instances in the region configured
        with this awsh_client instance.

        @finish_callback: the callback to call after the server replies with an answer

        @returns request id which represents this operation"""
        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        # Send command to server
        argument_string="{}".format(self.region)
        self.send_client_command(command=awsh_server_commands.QUERY_REGION,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id

    def __choose_with_rofi(self, rofi_title, entries, custom_entry = ""):

        r = Rofi()
        items_desc = list()
        items = list()
        for item, desc in entries.items():
            items.append(item)
            item_desc = ""
            if 'color' in desc:
                item_desc = r'<span background="{}">    </span>    '.format(desc["color"])

            item_desc = item_desc + desc['title']
            items_desc.append(item_desc)
            pass

        if custom_entry != "":
            items_desc.append(custom_entry)

        index, key = r.select('Choose interface to attach', items_desc)

        # the user canceled its choice
        is_err = key != 0
        custom_choice = index == len(items)

        return is_err, custom_choice, index

    def __get_available_interface_in_az_list(self, az):
        """This functions returns two lists containing the available ENIs
        in the provided availability zone
        @az - the availability zone to search available ENIs in

        @returns a (@enis_ids, @enis_strings) tuple where
           @enis_ids     - the ids of the available enis
           @enis_strings - formatted strings of the available enis """

        interfaces = self.interfaces

        subnet_color_dict = self.subnet_color_dict
        possible_interfaces = []
        interfaces_desc = []
        for eni, interface in interfaces.items():
            status = interface['status']
            if_az = interface['az']
            if status == 'available' and if_az == az:
                # this array holds is the same as the one display to the user,
                # but with eni ids instead of their description
                possible_interfaces.append(eni)

                subnet_id = interface['subnet']
                if not subnet_id in subnet_color_dict:
                    new_color = SUBNET_COLORS[ len(subnet_color_dict) % len(SUBNET_COLORS) ]
                    subnet_color_dict[subnet_id] = new_color

                subnet_color = subnet_color_dict[subnet_id]

                # Each entry would begin with the color of its subnet
                interface_desc = r'<span background="{}">    </span>'.format(subnet_color)
                interface_desc = interface_desc + "    " + interface['description']

                interfaces_desc.append(interface_desc)

        return possible_interfaces, interfaces_desc

    def choose_subnet_name(self, az):
        subnets = dict()
        for interface in self.interfaces.values():
            if interface['az'] != az:
                continue

            subnet_id = interface['subnet']
            subnet_color_dict = self.subnet_color_dict
            subnet = subnets.get(
                subnet_id,
                { 'interface_nr': 0 }
            )

            # TODO: The only reason there isn't a function for this operation is
            # because it needs to be somehow share with the GUI part.
            # Maybe leave all color related decisions to client module?
            if not subnet_id in subnet_color_dict:
                new_color = SUBNET_COLORS[ len(subnet_color_dict) % len(SUBNET_COLORS) ]
                subnet_color_dict[subnet_id] = new_color
            
            subnet['color'] = subnet_color_dict[subnet_id]
            nr_infs = subnet['interface_nr'] = subnet['interface_nr'] + 1
            subnet['title'] = str(subnet_id) + f" : {nr_infs} interfaces"
            subnets[subnet_id] = subnet

        is_err, custom_choice, subnet_ix = self.__choose_with_rofi(
            "Choose a subnet to create ENIs in",
            subnets,
            "Create new subnet")

        # TODO: it makes sense to raise an exception for this error. It would
        # save propagating the error oursevles
        if is_err:
            return is_err, None, None

        if custom_choice:
            az_letter = az[-1]
            custom_choice = f"subnet-{az_letter}-"
            # the server would search for a subnet_ix which ensures the name
            # doesn't clush with existing subnet
            custom_choice = custom_choice + "{subnet_ix}"

        return is_err, custom_choice, subnet_ix 

    def connect_eni(self, instance, finish_callback=None):

        instance_az = instance['placement']['AvailabilityZone']

        r = Rofi()
        interfaces = self.interfaces

        possible_interfaces, interfaces_desc = self.__get_available_interface_in_az_list(instance_az)
        interfaces_desc.append("Create new interface")

        # choose an interface from possibilities
        index, key = r.select('Choose interface to attach', interfaces_desc)

        # the user canceled its choice
        if key != 0:
            return None, None

        # The user chose an existing interface (instead of creating a new one
        if index < len(possible_interfaces):

            print("Chose ENI", possible_interfaces[index])

            # We chose an interface, we mark it as pending
            eni = possible_interfaces[index]
            interface = interfaces[eni]
            # TODO: This needs a more robust mechanism. Mark it as pending and check
            # attach status to know if it's available
            interface['status'] = 'in-use'
        else:
            # TODO: This would need to be both create ENI and attach a new one.
            # For now, just create a new one and exit
            eni = None

        # increase the number of enis connected to client
        num_interface = instance['num_interfaces']
        instance['num_interfaces'] = num_interface + 1

        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        if index < len(possible_interfaces):
            # The user wants to connect an existing ENI
            argument_string="{} {} {} {}".format(self.region, instance['id'], eni, num_interface)
            self.send_client_command(command=awsh_server_commands.CONNECT_ENI,
                                     arguments=argument_string, request_id=request_id, handler=finish_callback)
        else:
            # The user wants to create a new ENI and subnet
            # TODO: need to support existing subnet as well (and then the option
            # to find the propper ENI names)
            # ALSO: need to find a way to properly choose a subnet name
            
            is_err, new_subnet_name, subnet_ix = self.choose_subnet_name(instance_az)

            if is_err:
                return None, None

            # The user wants to create a new subnet
            if new_subnet_name:
                print("region is {}".format(instance_az))
                az_letter = instance_az[-1]
                # subnet_name = new_subnet_name
                stub = "{subnet_ix}"
                enis_names = f"testing-{az_letter}{stub}-i1 testing-{az_letter}{stub}-i2"
                print(f"Creating subnet by name templace: {new_subnet_name}")
                print(f"Creating enis: by name templates {enis_names}")

                argument_string="{} {} {} {}".format(self.region, instance_az, new_subnet_name, enis_names)
                self.send_client_command(command=awsh_server_commands.CREATE_ENI_AND_SUBNET,
                                         arguments=argument_string, request_id=request_id, handler=finish_callback)
            else:
                # TODO: implemente the case of choosing existing subnet
                pass

            interface = ""

        return request_id, interface


    def detach_all_enis(self, instance, finish_callback):
        instance_id = instance['id']

        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        # Send command to server
        argument_string="{} {}".format(self.region, instance_id)
        self.send_client_command(command=awsh_server_commands.DETACH_ALL_ENIS,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id


    def __get_login_and_kernel_by_ami_name(self, ami_name : str):
        """Try to guess the distribution login username based on the ami name.
        if not found, return 'ec2-user'"""
        ami_name = ami_name.lower()

        if 'amzn' in ami_name or re.search(r'\bal\b', ami_name):
            return 'ec2-user', 'linux'
        elif 'ubuntu' in ami_name:
            return 'ubuntu', 'linux'
        elif 'sles' in ami_name:
            return 'ec2-user', 'linux'
        elif 'rhel' in ami_name:
            return 'ec2-user', 'linux'
        elif 'fedora' in ami_name:
            return 'fedora', 'linux'
        elif 'debian' in ami_name:
            return 'debian', 'linux'
        elif 'centos' in ami_name:
            return 'centos', 'linux'
        elif 'macos' in ami_name:
            return 'ec2-user', 'macos'

        return 'ec2-user', 'linux'


    def index_instance(self, instance, finish_callback):
        ami_name    = instance['ami_name']
        print(f'ami name is {ami_name}')

        username, kernel = self.__get_login_and_kernel_by_ami_name(ami_name)

        print(f'username is {username}, kernel is {kernel}')
        server      = instance['public_dns']
        key         = instance['key']

        index = find_in_saved_logins(server = server, username = username,
                                     key = key, kernel = kernel, add_if_missing = True)

        finish_callback(index)

        return index
