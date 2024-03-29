from os.path import expanduser
import json
import os

INSTANCES_DIR = expanduser("~") + '/saved_instances'
LOGIN_FILE = INSTANCES_DIR + '/saved_logins'

KEYS_DIR = expanduser("~") + '/keys'

SUBNET_COLORS = ['#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5', '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5']
subnets_colors = dict()
def awsh_get_subnet_color(region : str, subnet_id : str):
    """Return a color for a specific region and subnet strings. The same color would
    be returned from all invocations with the same arguments"""
    region_colors = subnets_colors.get(region, dict())
    subnets_colors[region] = region_colors
    
    if subnet_id not in region_colors:
        new_color = SUBNET_COLORS[len(region_colors) % len(SUBNET_COLORS)]
        region_colors[subnet_id] = new_color

    return region_colors[subnet_id]


def clean_saved_logins():
    open(LOGIN_FILE, 'w').close()


# TODO: maybe add an option to insert an entry from the start ?
# This would allow to add new entries w/o deleting saved_logins
# content each time (what would you do it the entry is already
# there ? Move it to be the first entry ? is it
# likely to matter if you leave it there ?)
def find_in_saved_logins(server, username=None, key=None, kernel="",
                         ami_name="", add_if_missing=False):
    if len(server) == 0:
        return '-'

    if not os.path.exists(INSTANCES_DIR):
        os.mkdir(INSTANCES_DIR)

    # create the login file if it doesn't exist
    with open(LOGIN_FILE, "a"):
        pass

    with open(LOGIN_FILE, "r+") as lfile:
        line_nr = 1
        for line in lfile:
            if server in line:
                return line_nr

            line_nr += 1

    if add_if_missing and (not username or not key):
        print("Need username and key to add non-existing entry to logins")
        return '-'

    if not add_if_missing:
        return '-'

    with open(LOGIN_FILE, "a") as lfile:
        key_path = '{}/{}.pem'.format(KEYS_DIR, key)
        entry = {
            "username": username,
            "server": server,
            "key": key_path,
            "kernel": kernel,
            "ami_name": ami_name
        }

        lfile.write("{}\n".format(json.dumps(entry)))

    return line_nr


def get_entry_at_index(index):
    """Return the json entry for a given index or None if index isn't valid"""
    if not isinstance(index, int):
        return None

    with open(LOGIN_FILE, "r") as lfile:
        lines = lfile.readlines()
        if len(lines) <= index:
            return None

        line = lines[index]

    return json.loads(line)


def main():
    # login_entry = find_in_saved_logins('ec2-user@ec2-3-249-88-111.eu-west-1.compute.amazonaws.com', username='shay', key='northvirginia', add_if_missing = False)
    # login_entry = find_in_saved_logins('ec2-55-175-193-47.compute-1.amazonaws.com', username='shay', key='northvirginia', add_if_missing = True)
    # login_entry = find_in_saved_logins('', username='shay', key='northvirginia', add_if_missing = False)
    # print("Login is in entry", str(login_entry))

    login = get_entry_at_index(0)
    print(login)


if __name__ == '__main__':
    main()
