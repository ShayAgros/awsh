import boto3
# TODO: maybe move all such exceptions to Aws class, and have your own defined
# exceptions ?
import botocore.exceptions
import threading
import signal, sys
import time
from datetime import datetime
import psutil
import json

from pid import PidFile

from awsh_ec2 import Aws
from awsh_cache import awsh_cache
from awsh_req_resp_server import start_requests_server, awsh_req_server, awsh_connection

import logging, coloredlogs

# TODO: separate the request handler and the synchronous update into two
# functions. They don't share anything in common except shared access to boto3

intervals = {
    # TODO: not used, maybe remove it completely
    "instance_in_pref_regions"  : 3600 * 1,
    "instance_in_all_regions"   : 3600 * 8,
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
    DETACH_ALL_ENIS=5

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

        coloredlogs.DEFAULT_LOG_FORMAT = '%(asctime)s %(name)-20s %(levelname)s %(message)s'
        coloredlogs.install(level="INFO", stream=sys.stdout)

        self.logger = logging.getLogger("awsh-server")

    def start_requests_server(self):
        if not self.req_resp_server_running:
            self.req_resp_server_running = True
            self.req_server = awsh_req_server(self)
            req_server_thread = threading.Thread(target=lambda: start_requests_server(self.req_server))
            req_server_thread.start()

    def process_request(self, request: list, connection: awsh_connection):
        """This function is the needs to be implemented for awsh_req_server.  It
        is called each time a request is submitted.
            
            @request:       An array of words
            @connection:    Object upon which call complete_request once the
                            operation is completed 
           
           """
        logger = self.logger

        logger.info("aws_server: received command {}".format(request[0]))
        # will be overridden depending on the request
        reply = ''

        if request[0] == str(awsh_server_commands.QUERY_REGION):
            region = request[1]

            logger.info('aws_server: asked to query region {}'.format(request[1]))

            instances, has_running_instances = self.ec2.query_instances_in_regions([region])
            reply = json.dumps(instances[region])

            cache = self.cache

            cache.set_instances(instances)
            cache.set_is_running_instances(has_running_instances)

        elif request[0] == str(awsh_server_commands.START_INSTANCE):
            region = request[1]
            instance_id = request[2]

            logger.info('aws_server: starting instance {} in region {}'.format(instance_id, region))
            instance_info = self.ec2.start_instance(instance_id, region, wait_to_start=True)

            cache = self.cache

            cache.set_instance(instance_info, region, is_running=True)

            # TODO: This is wasteful to send all instances on the socket. Also
            # it allows a race. Fix it
            reply = json.dumps(cache.get_instances(region))

        elif request[0] == str(awsh_server_commands.STOP_INSTANCE):
            region = request[1]
            instance_id = request[2]

            logger.info('aws_server: stopping instance {} in region {}'.format(instance_id, region))
            self.ec2.stop_instance(instance_id, region, wait_until_stop=False)
        elif request[0] == str(awsh_server_commands.CONNECT_ENI):
            region      = request[1]
            instance_id = request[2]
            eni         = request[3]
            index       = int(request[4])

            self.ec2.connect_eni_to_instance(region, index, instance_id=instance_id, eni_id=eni)
        elif request[0] == str(awsh_server_commands.DETACH_ALL_ENIS):
            region      = request[1]
            instance_id = request[2]

            # TODO: this currently results in a query done to the server to find
            # what interfaces are attached. This information should already be
            # available to the server. It can specify the ENIs to detach to the
            # function
            detached_enis = self.ec2.detach_private_enis(region, instance_id)

            if detached_enis:
                reply = json.dumps(detached_enis)

        else:
            logger.error('aws_server: unknown command {}'.format(request[0]))

        connection.complete_request(reply=reply)

    def query_info(self):

        logger = self.logger

        while not server_stop:
            
            time.sleep(5)
            # TODO: is there any benefit to having it cached ?
            ec2 = self.ec2
            
            cache = self.cache

            current_time = datetime.now()

            # TODO: Maybe move the intervals struct to aws_cache ?
            if cache.is_record_old_enough(current_time, intervals, 'instance_in_all_regions'):
                logger.info("querying all instances")

                try:
                    all_instances, has_running_instances = ec2.query_all_instances()
                except botocore.exceptions.EndpointConnectionError as err:
                    logger.warning("Failed to query EC2 due to internet failure")
                    continue

                cache.set_instances(all_instances)
                cache.set_is_running_instances(has_running_instances)

                cache.update_record_ts('instance_in_all_regions', current_time.timestamp())
                cache.update_record_ts('instance_in_pref_regions', current_time.timestamp())
                logger.info('done querying all instances')
            # elif cache.is_record_old_enough(current_time, intervals, 'instance_in_pref_regions'):
                # print("querying preferred instances", end=' - ', flush = True)

                # preferred_instances, has_running_instances = ec2.quary_preferred_regions()

                # cache.set_instances(preferred_instances)
                # cache.set_is_running_instances(has_running_instances)

                # cache.update_record_ts('instance_in_pref_regions', current_time.timestamp())
                # print('done')

            if cache.is_record_old_enough(current_time, intervals, 'interfaces_in_all_regions'):
                logger.info("querying all interfaces")

                try:
                    all_interfaces = ec2.query_all_interfaces()
                except botocore.exceptions.EndpointConnectionError as err:
                    logger.warning("Failed to query EC2 due to internet failure")
                    continue

                # We allow the awsh_client to decide itself whether an interface
                # is free or not based on the instance's attached ENIs. Denote
                # all interfaces as free
                for enis in all_interfaces.values():
                    for eni in enis.values():
                        eni['status'] = 'available'

                self.cache.set_interfaces(all_interfaces)

                cache.update_record_ts('interfaces_in_all_regions', current_time.timestamp())
                logger.info("done querying all interfaces")

            # update fail because of locking, retry again next time
            # TODO: maybe rename to something clearer
            cache.update_cache()

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
            print("Starting aws helper server")

            server.start_server()
    except Exception as e:
        print("Daemon is already running")
        print(e)
