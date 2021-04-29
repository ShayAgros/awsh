import fcntl, os
import os.path as path
import json

cache_dir = path.expanduser('~/') + ".cache/awsh"
cache_file = cache_dir+ "/info"

def update_cache(updated_data):

    if not path.exists(cache_dir):
        os.makedirs(cache_dir)

    # duplicate logic to avoid locking a non-existent file
    if not path.isfile(cache_file):
        with open(cache_file, 'w') as f:
            json.dump(updated_data, f, indent=4)
        return True

    with open(cache_file, 'w') as f:
        try:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except:
            return False

        json.dump(updated_data, f, indent=4)

        try:
            fcntl.lockf(f, fcntl.LOCK_UN)
        except:
            print("Failed to unlock for some reason")

    return True

def read_cache():
    cached_info = None

    if not path.exists(cache_dir):
        os.makedirs(cache_dir)

    if not path.isfile(cache_file):
        return dict()

    with open(cache_file, 'r') as f:
        try:
            fcntl.lockf(f, fcntl.LOCK_SH)
        except:
            cached_info = None

        cached_info = json.load(f)

        try:
            fcntl.lockf(f, fcntl.LOCK_UN)
        except:
            print("Failed to unlock for some reason")
    
    return cached_info
