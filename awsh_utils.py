from os.path import expanduser
import json
import os
import re

INSTANCES_DIR = expanduser("~") + '/saved_instances'
LOGIN_FILE = INSTANCES_DIR + '/saved_logins'

KEYS_DIR = expanduser("~") + '/workspace/keys'

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


def get_os_by_ami_name(ami_name: str):
    """Try to guess the distribution login username based on the ami name.
    if not found, return 'ec2-user'"""
    ami_name = ami_name.lower()

    ubuntu_ver = re.findall("ubuntu[a-z-]+([0-9.]+)", ami_name)
    if ubuntu_ver:
        return f"ubuntu {ubuntu_ver[0]}"
    if 'ubuntu' in ami_name:
        return "ubuntu"
    if 'macos' in ami_name:
        return 'macos'
    if 'al2023' in ami_name:
        return "al2023"
    if 'amzn2' in ami_name:
        return "al2"
    if 'amzn' in ami_name or re.search(r'\bal\b', ami_name):
        return 'al1'
    if 'sles' in ami_name:
        return "sles"
    rhel_ver = re.findall("rhel[a-z-_]+([0-9.]+)", ami_name)
    if rhel_ver:
        return f"rhel {rhel_ver[0]}"
    if 'rhel' in ami_name:
        return "rhel"
    if 'fedora' in ami_name:
        return "fedora"
    if 'debian' in ami_name:
        return 'debian'
    if 'centos' in ami_name:
        return 'centos'
    fbsd_ver = re.findall("freebsd ([0-9.]+)", ami_name)
    if fbsd_ver:
        return f"FreeBSD {fbsd_ver[0]}"
    if 'freebsd' in ami_name:
        return "FreeBSD"

    if 'nixos' in ami_name:
        return "NixOS"

    if 'arch-linux' in ami_name:
        return "Arch Linux"

    # this will truncate the string but it's better than
    # ending up with a string that spans several lines
    return ami_name[-20:]


def get_login_and_kernel_by_ami_name(ami_name: str):
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
    elif 'nixos' in ami_name:
        return 'root', 'linux'
    elif 'arch-linux' in ami_name:
        return 'arch', 'linux'

    return 'ec2-user', ''


def get_available_interface_in_az_list(interfaces : dict, instances : list, az : str) -> list:
    """This functions returns a list containing the available ENIs
    in the provided availability zone
    @interfaces: dictionary of interfaces as defined created by the awsh_server
    class
    @az: the availability zone to search available ENIs in

    @returns a @enis_ids list"""

    # create a set of all interfaces that are already connected
    used_interfaces = set()
    for instance in instances:
        if instance["az"] != az:
            continue

        for interface in instance["interfaces"]:
            used_interfaces.add(interface["id"])

    possible_interfaces = []
    for eni, interface in interfaces.items():
        status = interface['status']
        interface_az = interface['az']

        # these are interfaces created by default. Don't count them
        if interface['delete_on_termination']:
            continue

        if interface_az != az:
            continue

        if eni in used_interfaces:
            continue

        possible_interfaces.append(eni)

    return possible_interfaces


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
        return None

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
        return None

    if not add_if_missing:
        return None

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
