import boto3
import threading
import signal, sys
import time
from datetime import datetime
import psutil
import json

from pid import PidFile

from awsh_ec2 import Aws
from awsh_cache import update_cache, read_cache
from awsh_req_resp_server import start_requests_server, awsh_req_server

# TODO: separate the request handler and the synchronous update into two
# functions. They don't share anything in common except shared access to boto3

intervals = {
    "instance_in_pref_regions": 3600 * 1,
    "instance_in_all_regions" : 3600 * 3,
    # "all_amis": 3600 * 24,
    # "all_instance_size": 3600 * 24, 
    }

class awsh_server_commands():
    QUERY_REGION=1
    START_INSTANCE=2
    STOP_INSTANCE=3

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

    def is_record_old_enough(self, ts_dict, record):
        if not record in ts_dict:
            return True
        
        ts = ts_dict[record]
        prev_time = datetime.fromtimestamp(ts)

        return (self.current_time - prev_time).seconds >= intervals[record]
    
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

            regions = self.ec2.query_instances_in_regions([region])
            # TODO: Such accesses to region are error prone
            # You need to define a set of functions for ec2 module which returns
            # the information for each such field
            reply = json.dumps(regions[region]['instances'])

            # TODO: this approach isn't robust enough and I don't like it. We
            # hold a lock for a whole file when we want to update a single
            # region (though does it really matter if we hold the lock for a
            # single entry or the whole file performance wise?)
            #
            # Idea: since you won't to avoid concurrent ec2 updates maybe we can
            # ask it to hold the persistent data ?
            
            info = read_cache()
            if not 'regions' in info:
                info['regions'] = dict()
            if not region in info['regions']:
                info['regions'][region] = dict()

            info['regions'][region]['instances'] = regions[region]['instances']
            # note that this might fail
            update_cache(info)
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
        else:
            print('aws_server: unknown command', request[0])

        connection.complete_request(reply=reply)


    def query_info(self):

        while not server_stop:
            
            time.sleep(1)

            ec2 = self.ec2
            
            info = read_cache()
            if info is None:
                continue

            if not 'ts_dict' in info:
                info['ts_dict'] = dict()

            # the private struct would allow us to track when we queried each
            # value last time
            ts_dict = info['ts_dict']
            self.current_time = datetime.now()

            if self.is_record_old_enough(ts_dict, 'instance_in_all_regions'):
                print("querying all instances", end=' - ', flush = True)
                info['regions'] = ec2.query_all_instances()
                ts_dict['instance_in_all_regions'] = self.current_time.timestamp()
                ts_dict['instance_in_pref_regions'] = self.current_time.timestamp()
                print('done')
            elif self.is_record_old_enough(ts_dict, 'instance_in_pref_regions'):
                print("querying preferred instances", end=' - ', flush = True)

                preferred_instances = ec2.quary_preferred_regions()

                if not 'regions' in info:
                    info['regions'] = dict()

                for region in preferred_instances.keys():
                    info['regions'][region]['instances'] = preferred_instances[region]['instances']

                ts_dict['instance_in_pref_regions'] = self.current_time.timestamp()
                print('done')

            # update fail because of locking, retry again next time
            update_cache(info)

        # kill request server as well
        self.req_server.handle_close()

    def start_server(self):
        if not self.query_info_running:
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
