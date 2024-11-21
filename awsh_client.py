from typing import Union, Callable

from awsh_req_resp_server import awsh_req_client
from awsh_server import awsh_server_commands
from awsh_utils import (find_in_saved_logins,
                        awsh_get_subnet_color)
from awsh_ui import awsh_rofi

import json
import re


# TODO: this probably needs to be integrated into the client
def get_current_state(req_client = None):
    # from awsh_cache import awsh_cache

    # cache = awsh_cache()
    # if not cache.read_cache():
        # print("Failed to read cache")
    # return cache.get_instances()

    req_client = awsh_req_client(fail_if_no_server=True, synchronous=True)
    command = awsh_server_commands.GET_CURRENT_COMPLETE_STATE
    request = '{}'.format(command)

    # import pickle

    # ignore server's request failure (we assume that it cannot happen)
    _, server_reply = req_client.send_request_blocking(request)
    return json.loads(server_reply)


CLIENT_CALLBACK=Callable[[int, int, Union[dict,None]], None]

class awsh_client:
    """This class is the counterpart of awsh_server. Its purpose is to send
    requests to it and process its reply. It shouldn't be used without a running
    server"""

    def __init__(self, region : str, instances : list,
                 interfaces : dict,
                 synchronous : bool = False):
        # state variable. Holds current regions state
        self.region = region

        self.instances = instances
        self.interfaces = interfaces

        # self.remove_used_interfaces_from_pool()

        self.next_req_id = 0

        self.synchronous = synchronous

        # TODO: why is it actually needed ? A client could be initialized
        # without any data, and it's ok
        # if not instances or not interfaces:
            # self.query_region_state()

    def query_region_state(self):
        if not self.synchronous:
            raise Exception("No instances and subnets for asynchronous client")

        # TODO: finish later
        argument_string = f"{region}"
        # self.send_client_command(
            # command=awsh_server_commands.START_INSTANCE,
            # arguments=argument_string, request_id=request_id)

    def get_req_id(self):
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        return request_id

    def remove_used_interfaces_from_pool(self):
        """Mark interfaces which are attached to interfaces as used. This way
        they won't be presented as an option when connecting an interface"""

        for instance in self.instances:
            try:
                for interface in instance['interfaces']:
                    eni = interface['id']
                    # default interfaces not always listed in interfaces or the data
                    # might be stale
                    if eni in self.interfaces:
                        self.interfaces[eni]['status'] = "in-use"

            except KeyError as e:
                print(f"Couldn't find key \"{e.args[0]}\" in {instance['id']} for region {self.region}")


    def send_client_command(self, command, arguments, request_id,
                            handler : Union[CLIENT_CALLBACK, None] = None):
        try:
            req_client = awsh_req_client(synchronous=self.synchronous)
            request = '{} {}'.format(command, arguments)

            # this function is called by the request client
            # after it finishes its connection with the server
            # TODO: Does this function needs to be inlined ?
            # (does it access some variables in the parent function ? If not
            # worth moving it to have smaller indentation)
            def handle_reply(connection : awsh_req_client,
                             response_status : int,
                             server_reply : str):

                # we maintain a connection per-request
                if not self.synchronous:
                    connection.close()

                if response_status != 0:
                    print("request id {} failed with status {} and reply {}".format(
                          request_id, response_status, server_reply))

                server_dict = dict()

                # transform reply back to json format
                if response_status == 0 and server_reply != "":
                    try:
                        server_dict = json.loads(server_reply)
                    except:
                        # TODO: Check that it's actually a json error. This is
                        # just ridicules that you fail for any exception
                        print("Couldn't transform reply into json. reply:")
                        print(server_reply)
                        server_dict = dict()

                if handler is None:
                    if not self.synchronous:
                        return

                    return response_status, server_dict

                handler(request_id,
                        response_status,
                        server_dict)

                return

            if not self.synchronous:
                req_client.send_request(request, handle_reply)
            else:
                response_status, server_reply = req_client.send_request_blocking(request)
                return handle_reply(None, response_status, server_reply)

        except Exception as exc:
            print("aws_client: failed to start connection")
            raise exc
            return
        pass

    
    def set_instance_state(self, instance, state : int,
                           finish_callback : Union[CLIENT_CALLBACK, None]):
        """Modify the current instance state
        state: one of fallowing values
            0: start instance
            1: shutdown instance
            2: reboot instance
            3: terminate instance"""

        commands = awsh_server_commands

        # currently these two commands alone are supported
        if state == 0:
            command = commands.START_INSTANCE
        elif state == 1:
            command = commands.STOP_INSTANCE
        else:
            if finish_callback:
                finish_callback(0, 1, None)
            return

        def set_state_cb(request_id, status, instances):
            if status != 0:
                return

            # NULL or empty dictionary means the sever has no update for
            # our instances state
            if instances:
                self.instances = instances

            if finish_callback:
                finish_callback(request_id, status, instances)

        # assign request id
        request_id = self.get_req_id()
        argument_string="{} {}".format(self.region, instance['id'])
        self.send_client_command(
                command=command,
                arguments=argument_string, request_id=request_id,
                handler=set_state_cb)

        return request_id


    def start_instance(self, instance, finish_callback = None):
        instance_id = instance['id']

        # TODO: this cannot really be integrated because 'finish_callback'
        # receives argument which you don't pass. Also the self.instances struct
        # isn't updated across invocations
        def update_interface_state(finish_callback):
            """Update the available interface lists"""
            # TODO: this is a silly solution. The server is the only one aware
            # that interfaces have been removed. it makes more sense that it'd
            # push a new state instead of the client guessing that
            # for eni, interface in self.interfaces.items():
                # self.interfaces[eni]['status'] = "available"

            if finish_callback is not None:
                finish_callback()

            self.remove_used_interfaces_from_pool()

        # assign request id
        request_id = self.get_req_id()

        # Send command to server
        argument_string="{} {}".format(self.region, instance_id)
        self.send_client_command(command=awsh_server_commands.START_INSTANCE,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id


    def stop_instance(self, instance, finish_callback = None):
        instance_id = instance['id']

        # assign request id
        request_id = self.get_req_id()

        # Send command to server
        argument_string="{} {}".format(self.region, instance_id)
        self.send_client_command(command=awsh_server_commands.STOP_INSTANCE,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id


    def refresh_instances(self, finish_callback : Union[CLIENT_CALLBACK, None]):
        """Send the server a request to query all instances in the region configured
        with this awsh_client instance.

        @finish_callback: the callback to call after the server replies with an answer

        @returns request id which represents this operation"""
        # assign request id
        request_id = self.get_req_id()

        def update_instances(request_id : int, status : int, instances : dict):
            if status == 0:
                self.instances = instances

            if finish_callback is not None:
                finish_callback(request_id, status, instances)

        # Send command to server
        argument_string="{}".format(self.region)
        self.send_client_command(command=awsh_server_commands.QUERY_REGION,
                arguments=argument_string, request_id=request_id, handler=update_instances)


    def _create_enis(self, subnet : dict, enis_names : list,
                     finish_callback = None):
        """Create ENIs:
        @subnet: subnet in which to create enis (a dictionary as received from
                 server)
        @enis_names: names of the ENIs to create
        """
        num_interface = len(enis_names)
        if num_interface <= 0:
            return None

        # assign request id
        request_id = self.get_req_id()

        argument_string="{} {} {} {}".format(
            self.region,
            subnet['id'],
            num_interface,
            " ".join(enis_names))

        self.send_client_command(
            command=awsh_server_commands.CREATE_ENIS,
            arguments=argument_string, request_id=request_id,
            handler=finish_callback)

        return request_id



    # TODO: maybe move it to server's side ? There's the color issue there
    # but you can have blocking connection here
    def __get_available_subnets_in_az_list(self, az):
        """This function returns a list of possible subnets in an
        availability zone.
        @az - the availability zone to search available subnets in

        @returns a @subnets_ids list of dictionaries where
        each entry is a dictionary with the entries:
        @entry : subnet id
        @color: subnet color"""
        az_subnets = dict()

        # find all subnets and their colors
        for interface in self.interfaces.values():
            if interface['az'] != az:
                continue

            subnet_id = interface['subnet']
            subnet = az_subnets.get(
                subnet_id,
                { 'interface_nr': 0 }
            )

            subnet_color = awsh_get_subnet_color(self.region, subnet_id)

            subnet['color'] = subnet_color
            nr_infs = subnet['interface_nr'] = subnet['interface_nr'] + 1
            az_subnets[subnet_id] = subnet

        possible_subnets = list()
        for subnet_id, subnet in az_subnets.items():
            # Not build an list from it for the UI system
            entry_title = f'{subnet_id} : {subnet["interface_nr"]} interfaces'
            entry = { "entry" : entry_title, "color" : subnet["color"]}
            possible_subnets.append(entry)

        return possible_subnets


    def _choose_subnet(self, az, finish_callback):

        r = awsh_rofi()
        possible_subnets = self.__get_available_subnets_in_az_list(az)

        add_new_eni_entry = { "entry" : "Create a new subnet" }
        possible_subnets.append(add_new_eni_entry)

        is_err, index = r.multiline_selection(
            "Choose a subnet to create ENIs in",
            possible_subnets)

        # TODO: it makes sense to raise an exception for this error. It would
        # save propagating the error oursevles
        if is_err:
            return None, None

        # create a new subnet
        if index == (len(possible_subnets) - 1):
            az_letter = az[-1]
            # the server would search for a subnet_ix which ensures the name
            # doesn't clush with existing subnet
            stub = "{subnet_ix}"
            new_subnet_name = f"subnet-{az_letter}-{stub}"
            enis_names = f"testing-{az_letter}{stub}-i1 testing-{az_letter}{stub}-i2"
            print(f"Creating subnet by name templace: {new_subnet_name}")
            print(f"Creating enis: by name templates {enis_names}")

            # execute a command
            request_id = self.next_req_id
            argument_string="{} {} {} {}".format(
                self.region, az, new_subnet_name, enis_names)
            self.send_client_command(
                command=awsh_server_commands.CREATE_ENI_AND_SUBNET,
                arguments=argument_string, request_id=request_id,
                handler=finish_callback)

            # TODO: If we want to add ENIs to newly created interfaces we
            # probably need to add some future handler to it.
            #
            # Probably would be part of "multi-step-execution notification
            # system where there's a task broken into several steps
            return None, None

        return None, None

    def connect_eni(self, instance_id, eni_id, device_ix, finish_callback):
        # assign request id
        request_id = self.get_req_id()

        argument_string="{} {} {} {}".format(self.region, instance_id, eni_id, device_ix)
        self.send_client_command(command=awsh_server_commands.CONNECT_ENI,
                                 arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id

    def create_subnet(self, az : str, finish_callback):
        az_letter = self.region[-1]

        subnet_stub = "{subnet_ix}"
        new_subnet_name = f"subnet-{az_letter}-{subnet_stub}"
        enis_names = f"testing-{az_letter}{subnet_stub}-i1 testing-{az_letter}{subnet_stub}-i2"
        print(f"Creating subnet by name templace: {new_subnet_name}")
        print(f"Creating enis: by name templates {enis_names}")

        request_id = self.get_req_id()
        argument_string="{} {} {} {}".format(self.region, az, new_subnet_name, enis_names)
        self.send_client_command(command=awsh_server_commands.CREATE_ENI_AND_SUBNET,
                                 arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id


    # def connect_eni(self, instance, finish_callback=None):

        # instance_az = instance['placement']['AvailabilityZone']

        # r = awsh_rofi()
        # interfaces = self.interfaces

        # possible_interfaces = self.__get_available_interface_in_az_list(instance_az)

        # new_eni_entry = { "entry" : "Create new interface" }
        # possible_interfaces.append(new_eni_entry)

        # # choose an interface from possibilities
        # is_error, index = r.multiline_selection('Choose interface to attach', possible_interfaces)

        # # user canceled the choice
        # if is_error:
            # return None, None

        # if index < (len(possible_interfaces) - 1):
            # # Chose an existing interface
            # interface = possible_interfaces[index]["interface"]
            # print("Chose ENI", interface["id"])

            # return self._connect_eni(instance, interface, finish_callback)

        # else: # new interface
            # subnet = self._choose_subnet(instance_az, finish_callback)
            # # new subnet was created
            # if subnet is None:
                # req_id = self.next_req_id
                # self.next_req_id = req_id + 1
                # return req_id, ""

            # # TODO: need to implement choosing exisitng subnet
            # return None

        # return request_id, interface


    def detach_all_enis(self, instance_id, finish_callback):
        # assign request id
        request_id = self.get_req_id()

        # Send command to server
        argument_string="{} {}".format(self.region, instance_id)
        self.send_client_command(command=awsh_server_commands.DETACH_ALL_ENIS,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id

    def __get_login_and_kernel_by_ami_name(self, ami_name: str):
        """Try to guess the distribution login username based on the ami name.
        if not found, return 'ec2-user'"""
        ami_name = ami_name.lower()

        if 'macos' in ami_name:
            return 'ec2-user', 'macos'
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
        # the word amzn can appear in multiple ami names. Better to check
        # for it last
        elif 'amzn' in ami_name or re.search(r'\bal\b', ami_name):
            return 'ec2-user', 'linux'

        return 'ec2-user', ''

    def index_instance(self, instance, finish_callback):
        ami_name = instance['ami_name']
        print(f'ami name is {ami_name}')

        username, kernel = self.__get_login_and_kernel_by_ami_name(ami_name)

        print(f'username is {username}, kernel is {kernel}')
        server = instance['public_dns']
        key = instance['key']

        index = find_in_saved_logins(
            server=server, username=username, key=key, kernel=kernel,
            ami_name=ami_name, add_if_missing=True)

        finish_callback(index)

        return index

    def get_instance_info_from_server_by_address(self, instance_dns: str):
        """Query AWSH server for a information about an instance based on its
           DNS address"""


def testing():
    import logging, coloredlogs, sys

    coloredlogs.DEFAULT_LOG_FORMAT = '%(asctime)s %(name)-20s %(levelname)s %(message)s'
    coloredlogs.install(level=logging.DEBUG, stream=sys.stdout)

    client = awsh_client("ap-northeast-2", [], {},  synchronous=True)

    def print_output(request_id,
                     response_success,
                     server_reply):
        print(json.dumps(server_reply, indent=4))

    client.refresh_instances(finish_callback=print_output)

if __name__ == '__main__':
    testing()
