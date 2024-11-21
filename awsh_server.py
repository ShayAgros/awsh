# TODO: maybe move all such exceptions to Aws class, and have your own defined
# exceptions ?
import botocore.exceptions as be
import threading
import signal
import time
from datetime import datetime
import json

from pid import PidFile

from awsh_ec2 import Aws
from awsh_cache import awsh_cache
from awsh_req_resp_server import start_requests_server, awsh_req_server, awsh_connection

import logging

# TODO: separate the request handler and the synchronous update into two
# functions. They don't share anything in common except shared access to boto3

intervals = {
    # TODO: not used, maybe remove it completely
    "regions_get_long_name"     : 3600 * 24 * 30,
    "instance_in_pref_regions"  : 3600 * 1,
    "instance_in_all_regions"   : 3600 * 8,
    "interfaces_in_all_regions" : 3600 * 24 * 2,
    "subnets_in_all_regions"    : 3600 * 24 * 2,
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
    CREATE_ENIS=5
    CREATE_SUBNET=6
    CREATE_ENI_AND_SUBNET=7
    DETACH_ALL_ENIS=8
    GET_CURRENT_REGION_STATE=9
    GET_CURRENT_COMPLETE_STATE=10
    GET_SUBNETS=11

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

        self.logger = logging.getLogger("awsh-server")

        if not self.cache.read_cache():
            self.logger.error("Failed to read cache. Terminating")
            raise Exception("Cache is busy")

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
        cache  = self.cache

        logger.debug("aws_server: received command {}".format(request[0]))
        # will be overridden depending on the request
        reply = ''

        if request[0] == str(awsh_server_commands.QUERY_REGION):
            region = request[1]

            logger.info('asked to query region {}'.format(request[1]))

            instances, has_running_instances = self.ec2.query_instances_in_regions([region])
            # TODO: Following snippet is for testings
            # instances = {}
            # has_running_instances = {}
            # instances[region] = cache.get_instances(region)
            # has_running_instances[region] = True

            reply = json.dumps(instances[region])

            cache.set_instances(instances)
            cache.set_is_running_instances(has_running_instances)

            logger.debug('finished querying region')

        elif request[0] == str(awsh_server_commands.START_INSTANCE):
            region = request[1]
            instance_id = request[2]

            logger.info('starting instance {} in region {}'.format(instance_id, region))
            instance_info = self.ec2.start_instance(instance_id, region, wait_to_start=True)

            cache.set_instance(instance_info, region, is_running=True) # type: ignore

            # TODO: This is wasteful to send all instances on the socket. Also
            # it allows a race. Fix it
            reply = json.dumps(cache.get_instances(region))

            logger.debug('finished starting instance {} in region {}'.format(instance_id, region))

        elif request[0] == str(awsh_server_commands.STOP_INSTANCE):
            region = request[1]
            instance_id = request[2]

            logger.info('stopping instance {} in region {}'.format(instance_id, region))
            self.ec2.stop_instance(instance_id, region, wait_until_stop=False)

            logger.debug('finished stopping instance {} in region {}'.format(instance_id, region))
        elif request[0] == str(awsh_server_commands.CONNECT_ENI):
            region      = request[1]
            instance_id = request[2]
            eni         = request[3]
            index       = int(request[4])

            logger.info(f'connecting eni {eni} to instance {instance_id} (as index {index}) in region {region}')
            instance_info = self.ec2.connect_eni_to_instance(region, instance_id, eni, index)

            cache.set_instance(instance_info, region)
            reply = json.dumps(instance_info)

            logger.debug(f'finished connecting eni {eni} to instance {instance_id} (as index {index}) in region {region}')
        elif request[0] == str(awsh_server_commands.DETACH_ALL_ENIS):
            region      = request[1]
            instance_id = request[2]

            logger.info(f'detaching all enis from instance {instance_id} in region {region}')
            # TODO: this currently results in a query done to the server to find
            # what interfaces are attached. This information should already be
            # available to the server. It can specify the ENIs to detach to the
            # function
            detached_enis, instance_info = self.ec2.detach_private_enis(region, instance_id)

            reply_dict = {
                "detached_enis" : detached_enis,
                "instance" : instance_info
            }
            reply = json.dumps(reply_dict)

            logger.debug(f'detaching all enis from instance {instance_id} in region {region}')

        elif request[0] == str(awsh_server_commands.CREATE_ENIS):
            pass

        elif request[0] == str(awsh_server_commands.CREATE_ENI_AND_SUBNET):
            region                  = request[1]
            az                      = request[2]
            subnet_name_template    = request[3]
            interfaces_names        = request[4:]

            logger.info(f'create {len(interfaces_names)} enis with a new subnet template ({subnet_name_template}) by the names: {interfaces_names} in region {region} and az {az}')

            # find a number which can be added to the subnet
            subnets = self.ec2.query_subnets_in_regions([region])
            subnet_names = [ subnet['name'] for subnet in subnets[region].values() ]
            subnet_name = ''
            for i in range(1, 40):
                if subnet_name_template.format(subnet_ix=i) in subnet_names:
                    continue

                subnet_name = subnet_name_template.format(subnet_ix=i)
                interfaces_names = [name.format(subnet_ix=i) for name in interfaces_names]
                break

            if not subnet_name:
                raise Exception("Invalid subnet name")

            logger.info(f'Chosen subnet name is {subnet_name}')

            subnet = self.ec2.create_subnet(region, az, subnet_name)
            for inf_name in interfaces_names:
                self.ec2.create_interface(inf_name, subnet)

            interfaces = self.ec2.query_interfaces_in_regions([region])

            cache.set_interfaces(interfaces)
            reply = json.dumps(cache.get_region_data(region))

        elif request[0] == str(awsh_server_commands.GET_CURRENT_REGION_STATE):
            region = request[1]

            logger.info(f"asked for current state for region {region}")
            reply = json.dumps(cache.get_region_data(region))
        elif request[0] == str(awsh_server_commands.GET_CURRENT_COMPLETE_STATE):
            logger.info("asked for current complete state")
            reply = json.dumps(cache.get_instances())
        else:
            logger.error('aws_server: unknown command {}'.format(request[0]))

        logger.debug(f"Replying command {request[0]}")

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
                except (be.EndpointConnectionError, be.ConnectTimeoutError) as err:
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
                except (be.EndpointConnectionError, be.ConnectTimeoutError, be.ReadTimeoutError) as err:
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


            if cache.is_record_old_enough(current_time, intervals, 'regions_get_long_name'):

                logger.info("querying regions long names")

                try:
                    regions_long_names = ec2.get_regions_full_name()
                except (be.EndpointConnectionError, be.ConnectTimeoutError, be.ReadTimeoutError) as err:
                    logger.warning("Failed to query EC2 due to internet failure")
                    continue

                self.cache.set_regions_long_names(regions_long_names)

                cache.update_record_ts('regions_get_long_name', current_time.timestamp())
                logger.info("done querying regions long names")


            if cache.is_record_old_enough(current_time, intervals, 'subnets_in_all_regions'):

                logger.info("querying regions subnets")

                try:
                    subnets = ec2.query_all_subnets()
                except (be.EndpointConnectionError, be.ConnectTimeoutError, be.ReadTimeoutError):
                    logger.warning("Failed to query EC2 due to internet failure")
                    continue

                self.cache.set_subnets(subnets)

                cache.update_record_ts('subnets_in_all_regions', current_time.timestamp())
                logger.info("done querying subnet data")

            # update fail because of locking, retry again next time
            # TODO: maybe rename to something clearer
            if not cache.update_cache():
                logger.warning("Failed to update cache. Will try next iteration")

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
            self.query_info_timer.cancel()
            self.query_info_running = False

def start_server(args):
    """Query EC2 for information like existing instances, subnets
       available amis, available instance size etc.

       args is unused, but declared to be consistent with other awsh subcommands"""

    try:
        # This would prevent more than one process to be run
        with PidFile('awsh_server_daemon') as p:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            server = awsh_server()
            print("Starting aws helper server")

            server.start_server()
    except Exception as e:
        print("Daemon is already running")
        print(e)
