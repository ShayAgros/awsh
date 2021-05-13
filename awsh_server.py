import boto3
import threading
import signal, sys
import time
from datetime import datetime
import psutil
import json

from pid import PidFile

from awsh_ec2 import Aws
from awsh_cache import awsh_cache
from awsh_req_resp_server import start_requests_server, awsh_req_server

# TODO: separate the request handler and the synchronous update into two
# functions. They don't share anything in common except shared access to boto3

intervals = {
    "instance_in_pref_regions"  : 3600 * 1,
    "instance_in_all_regions"   : 3600 * 3,
    "interfaces_in_all_regions" : 3600 * 24 * 2,
    # "all_amis": 3600 * 24,
    # "all_instance_size": 3600 * 24, 
    }

def update(dict1, dict2):
    # Update all new/changes entries in dict2
    for k, v in dict2.items():
        if isinstance(v, dict):
            dict1[k] = update(dict1.get(k, {}), v)
        else:
            dict1[k] = v

    return dict1

class awsh_server_commands():
    QUERY_REGION=1
    START_INSTANCE=2
    STOP_INSTANCE=3
    CONNECT_ENI=4

server_stop = False

def signal_handler(sig, frame):
    print('Exiting server')
    global server_stop
    # exit the server gracefully
    server_stop = True

class awsh_server:

    def __init__(self):
        self.query_info_timer = threading.Timer(1, self.query_info)
        self.req_resp_server_running = False
        self.query_info_running = False
        self.ec2 = Aws()

        # the cache would hold the server's state
        self.cache = awsh_cache()
        self.cache.read_cache()

    def start_requests_server(self):
        if not self.req_resp_server_running:
            self.req_resp_server_running = True
            self.req_server = awsh_req_server(self)
            req_server_thread = threading.Thread(target=lambda: start_requests_server(self.req_server))
            req_server_thread.start()

    def process_request(self, request, connection):
        """This function is the needs to be implemented for awsh_req_server.  It
        is called each time a request is submitted.
            
            @request:       An array of words
            @connection:    Object upon which call complete_request once the
                            operation is completed 
           
           """

        print("aws_server: received command {}".format(request[0]))
        # will be overridden depending on the request
        reply = ''

        if request[0] == str(awsh_server_commands.QUERY_REGION):
            region = request[1]

            print('aws_server: asked to query region', request[1])

            instances, has_running_instances = self.ec2.query_instances_in_regions([region])
            reply = json.dumps(instances[region])

            cache = self.cache

            cache.set_instances(regions)
            cache.set_is_running_instances(has_running_instances)

        elif request[0] == str(awsh_server_commands.START_INSTANCE):
            region = request[1]
            instance_id = request[2]

            print('aws_server: starting instance {} in region {}'.format(instance_id, region))
            self.ec2.start_instance(instance_id, region, wait_to_start=True)

        elif request[0] == str(awsh_server_commands.STOP_INSTANCE):
            region = request[1]
            instance_id = request[2]

            print('aws_server: stopping instance {} in region {}'.format(instance_id, region))
            self.ec2.stop_instance(instance_id, region, wait_until_stop=False)
        elif request[0] == str(awsh_server_commands.CONNECT_ENI):
            region      = request[1]
            instance_id = request[2]
            eni         = request[3]
            index       = int(request[4])

            self.ec2.connect_eni_to_instance(region, index, instance_id=instance_id, eni_id=eni)
        else:
            print('aws_server: unknown command', request[0])

        connection.complete_request(reply=reply)


    def query_info(self):

        while not server_stop:
            
            # TODO: is there any benefit to having it cached ?
            ec2 = self.ec2
            
            cache = self.cache
            if not cache.read_cache():
                continue

            current_time = datetime.now()

            # TODO: Maybe move the intervals struct to aws_cache ?
            if cache.is_record_old_enough(current_time, intervals, 'instance_in_all_regions'):
                print("querying all instances", end=' - ', flush = True)

                all_instances, has_running_instances = ec2.query_all_instances()

                cache.set_instances(all_instances)
                cache.set_is_running_instances(has_running_instances)

                cache.update_record_ts('instance_in_all_regions', current_time.timestamp())
                cache.update_record_ts('instance_in_pref_regions', current_time.timestamp())
                print('done')
            elif cache.is_record_old_enough(current_time, intervals, 'instance_in_pref_regions'):
                print("querying preferred instances", end=' - ', flush = True)

                preferred_instances, has_running_instances = ec2.quary_preferred_regions()

                cache.set_instances(preferred_instances)
                cache.set_is_running_instances(has_running_instances)

                cache.update_record_ts('instance_in_pref_regions', current_time.timestamp())
                print('done')

            if cache.is_record_old_enough(current_time, intervals, 'interfaces_in_all_regions'):
                print("querying all interfaces", end=' - ', flush = True)

                all_interfaces = ec2.query_all_interfaces()

                self.cache.set_interfaces(all_interfaces)

                cache.update_record_ts('interfaces_in_all_regions', current_time.timestamp())
                print('done')

            # update fail because of locking, retry again next time
            # TODO: maybe rename to something clearer
            cache.update_cache()

            time.sleep(5)

        # kill request server as well
        self.req_server.handle_close()

    def start_server(self):
        if not self.query_info_running:
            # TODO: re-enable later
            self.start_requests_server()
            self.query_info_timer.start()
            self.query_info_running = True

    def stop_server(self):
        if self.query_info_running:
            self.query_info_timer.stop()
            self.query_info_running = False

def start_server(args):
    """Query EC2 for information like existing instances, subnets
       available amis, available instance size etc.

       args is unused, but declared to be consistent with other awsh subcommands"""
    try:
        # This would prevent more than one process to be ran
        with PidFile('awsh_server_daemon') as p:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            server = awsh_server()
            print("Starting server")

            server.start_server()
    except Exception as e:
        print("Daemon is already running")
        print(e)
