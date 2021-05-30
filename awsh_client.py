from awsh_req_resp_server import awsh_req_client
from awsh_server import awsh_server_commands

import json
from rofi import Rofi

# TODO: unify it to a single interface
SUBNET_COLORS = ['#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',] 

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
            def handle_reply(connection, server_reply):
                connection.close()
                if not handler is None:
                    try:
                        if server_reply != "":
                            reply = json.loads(server_reply)
                        else:
                            reply = dict()

                        handler(request_id = request_id, server_reply = reply)
                    except:
                        # TODO: Check that it's actually a json error. This is
                        # just ridicules that you fail for any exception
                        print ("Couldn't transform reply into json. reply:")
                        print(server_reply)
                        return

            req_client.send_request(request, handle_reply)
        except:
            print("aws_client: failed to start connection")
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
        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        # Send command to server
        argument_string="{}".format(self.region)
        self.send_client_command(command=awsh_server_commands.QUERY_REGION,
                arguments=argument_string, request_id=request_id, handler=finish_callback)

        return request_id

    def connect_eni(self, instance, finish_callback=None):

        instance_az = instance['placement']['AvailabilityZone']

        r = Rofi()
        interfaces = self.interfaces

        subnet_color_dict = self.subnet_color_dict
        possible_interfaces = []
        interfaces_desc = []
        for eni, interface in interfaces.items():
            status = interface['status']
            if_az = interface['az']
            if status == 'available' and if_az == instance_az:
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

        # choose an interface from possibilities
        index, key = r.select('Choose interface to attach', interfaces_desc)

        # the user canceled its choice
        if key != 0:
            return None, None

        print("Chose ENI", possible_interfaces[index])

        # We chose an interface, we mark it as pending
        eni = possible_interfaces[index]
        interface = interfaces[eni]
        # TODO: This needs a more robust mechanism. Mark it as pending and check
        # attach status to know if it's available
        interface['status'] = 'in-use'

        # increase the number of enis connected to client
        num_interface = instance['num_interfaces'] 
        instance['num_interfaces'] = num_interface + 1

        # assign request id
        request_id = self.next_req_id
        self.next_req_id = request_id + 1

        # Send command to server
        argument_string="{} {} {} {}".format(self.region, instance['id'], eni, num_interface)
        self.send_client_command(command=awsh_server_commands.CONNECT_ENI,
                arguments=argument_string, request_id=request_id, handler=finish_callback)
        
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
