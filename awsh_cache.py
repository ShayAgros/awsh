import fcntl, os
import os.path as path
from threading import Lock
from datetime import datetime
import json

cache_dir = path.expanduser('~/') + ".cache/awsh"
cache_file = cache_dir+ "/info"

def synchronize_with_lock(func):
    def synchronize(*args, **kwargs):
        cache = args[0]
        cache.lock.acquire()
        result = func(*args, **kwargs)
        cache.lock.release()

        return result

    return synchronize


# TODO: add decorator to all values that need synchronization
class awsh_cache:

    def __init__(self):
        self.cache = dict()

        self.lock = Lock()
        pass

    def create_cache(self):
        self.cache['regions'] = dict()
        self.cache['ts_dict'] = dict()

    # Only the synchronous server accesses these fields
    def is_record_old_enough(self, current_time, intervals, record):
            ts_dict = self.cache['ts_dict']
            if not record in ts_dict:
                return True
            
            ts = ts_dict[record]
            prev_time = datetime.fromtimestamp(ts)

            return (current_time - prev_time).seconds >= intervals[record]

    # Only the synchronous server accesses these fields
    def update_record_ts(self, record, ts):
        self.cache['ts_dict'][record] = ts

    def __set_field_in_region(self, region, field, value):
        if not region in self.cache['regions']:
            self.cache['regions'][region] = dict()

        self.cache['regions'][region][field] = value

    @synchronize_with_lock
    def __set_cache_entry(self, entry, values, region=None):
        """Set an entry in the cache, e.g. instances, interfaces or
        has_running_instances field

        @entry: the entry in the cache to set. e.g. instances/interfaces etc.
        @values(dict): the value of this entry
        @region: region(s) in in which the interfaces belong. This can be either
            a string for a single region, or a list in which case"""

        if region is None:
            for region in values.keys():
                self.__set_field_in_region(region=region, field=entry, value=values[region])
        elif isinstance(region, str):
            self.__set_field_in_region(region=region, field=entry, value=values)
        else:
            # this assignment have no effect other than to signify that we have
            # several regions
            regions = region
            for region in regions:
                self.__set_field_in_region(region=region, field=entry, value=values[region])

    def set_instances(self, instances, region=None):
        """Set list of instances in region(s) from cache
        @instances(dict): the instances in the region
        @region(str/list): region(s) in in which the instances belong. This can be either
            a string for a single region, or a list in which case
            @instances would be a dictionary with keys equal to @region elements"""
        self.__set_cache_entry('instances', instances, region)

    @synchronize_with_lock
    def set_instance(self, instance, region, is_running = False):
        """Update a single instance entry in the cache
        @instance: the instance data. This data should contain 'id' field
            which identifies its id
        @region: the instance's region
        @is_running: whether the instance is in a running state

        @return None
        """
        self.cache['regions'][region]['instances'][instance['id']] = instance
        self.cache['regions'][region]['has_running_instances'] |= is_running

    @synchronize_with_lock
    def get_instances(self, region=None):
        """Set list of instances in region from cache"""
        if region is None:
            # TODO: the returned values are different for this case (regions
            # would contain other things besides instances such as interfaces.
            # Maybe create a new dictionary and return it ?
            return self.cache['regions']
        else:
            try:
                return self.cache['regions'][region]['instances']
            except:
                return dict()

    def set_is_running_instances(self, states, region=None):
        """Set the state of running instances"""
        self.__set_cache_entry('has_running_instances', states, region)

    def set_interfaces(self, interfaces, region=None):
        """Set list of interfaces in region(s) from cache
        @interfaces: the interfaces in the region
        @region: region(s) in in which the interfaces belong. This can be either
            a string for a single region, or a list in which case
            @interfaces would be a dictionary with keys equal to @region elements"""
        self.__set_cache_entry('interfaces', interfaces, region)

    def set_regions_long_names(self, regions_long_names):
        """Set dict of regions long names (e.g. Oregon for us-west-2).

        @regions_get_long_name: dictionary of regions' long named. The key is
        the region short code (e.g. us-west-2)
        """
        self.__set_cache_entry('long_name', regions_long_names)

    @synchronize_with_lock
    def get_interfaces(self, region=None):
        """Set list of interfaces in region from cache"""
        if region is None:
            # TODO: the returned values are different for this case (regions
            # would contain other things besides interfaces such as interfaces.
            # Maybe create a new dictionary and return it ?
            return self.cache['regions']
        else:
            try:
                return self.cache['regions'][region]['interfaces']
            except:
                return dict()

    def update_cache(self):

        if not path.exists(cache_dir):
            os.makedirs(cache_dir)

        # duplicate logic to avoid locking a non-existent file
        if not path.isfile(cache_file):
            with open(cache_file, 'w') as f:
                json.dump(self.cache, f, indent=4)
            return True

        with open(cache_file, 'w') as f:
            try:
                fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except:
                return False

            json.dump(self.cache, f, indent=4)

            try:
                fcntl.lockf(f, fcntl.LOCK_UN)
            except:
                print("Failed to unlock for some reason")

        return True

    def read_cache(self):
        cached_info = None

        if not path.exists(cache_dir):
            os.makedirs(cache_dir)

        if not path.isfile(cache_file):
            self.create_cache()
            return True

        with open(cache_file, 'r') as f:
            try:
                fcntl.lockf(f, fcntl.LOCK_SH)
            except:
                return False

            cached_info = json.load(f)

            try:
                fcntl.lockf(f, fcntl.LOCK_UN)
            except:
                print("Failed to unlock for some reason")
        
        if not cached_info:
            return False

        self.cache = cached_info
        return True
