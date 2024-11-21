import argparse
import logging
import json
from collections import OrderedDict

from awsh_curses import awsh_curses, run_curses_command, enter_debug
from awsh_client import get_current_state, awsh_client
import awsh_cache

region=""

def create_choice_from_interfaces(subnets : dict, interfaces : dict):
    """Create a multi level dictionary as specified by awsh_ui
    multiwindow_selection function.

    @interfaces: the interfaces list as return by awsh_ec2 or by the awsh server

    @returns ( subnets_list, choice_entries )
    where

    @subnets_list: list of the received subnets
    @choice_entries: the multi-level list for multiwindow_selection

    entry i in the second list describes the subnet in the same index in the
    first list.
    """

    # initialize list of all subnets
    choices = dict()
    for id, subnet in subnets.items():
        desc = subnet['name']
        entry = f"{id} ({desc})" if desc else f"{id}"
        choices[id] = (entry, [])

    possible_interfaces = []
    for interface in interfaces.values():
        eni = interface['id']
        desc = interface['description']
        entry = f"{eni} ({desc})" if desc else f"{eni}"

        subnet_id = interface['subnet']
        subnet = choices[subnet_id]

        subnet[1].append(entry)

    # return result as a list instead of dictionary
    subnets_list = list()
    choice_list = list()
    for subnet_id, entry in choices.items():
        subnets_list.append(subnet_id)
        choice_list.append(entry)

    return subnets_list, choice_list


def get_interfaces_default_names(subnet : dict, interfaces : dict,
                                 interface_nr : int):
        az = subnet['az']
        az_number = az[-1]

        subnet_desc = subnet['name'] or subnet['id'][:12] + f"-{az_number}"

        interface_names = list()
        i = 1
        while interface_nr > 0:
            potential_name = f"{subnet_desc}-i{i}"
            i += 1
            if potential_name in interfaces:
                continue
            interface_names.append(potential_name)
            interface_nr -= 1

        return interface_names


def yes_no_confirm(stdscr):
    """ask yes or no question"""

    reply = ac.ask_question("\n\nOk (Y/n): ")

    if reply in ["Y", "y"]:
        return True

    return False

@run_curses_command
def create_intefaces(stdscr, output_stream, args):
    """handler for `awsh cli add_interface` command"""
    interfaces = None
    subnets = None

    logger = logging.getLogger("awsh cli")
    region = str(args.region)

    logger.debug(f"Starting create interfaces for region {region}")

    regions = None
    if not args.force_aws_ec2_mode:
        # client mode
        try:
            client = awsh_client(region, None, None, synchronous=True)
            regions = get_current_state()

            logger.debug("Contacted running server")

            if not region in regions:
                # logger.error("Cannot find region {region} in cache")
                return

            # TODO: maybe implement a client command to only get the intercaces?
            # Only matters to be analog to ec2 path.
            subnets = regions[region]['subnets']
            interfaces = regions[region]['interfaces']
        except ConnectionRefusedError as e:
            logger.info("No running server was found")
            if args.force_client_mode:
                logger.error("force client mode requested, terminating")
                return

    # either failed to contact client or asked to access ec2 directly
    if regions is None:
        # handle this part later
        return

    subnet_ids, entries = create_choice_from_interfaces(subnets, interfaces)
    # add an option to create a new subnet
    entries.append("Create new subnet")

    ac = awsh_curses(stdscr)
    is_err, chosen_values = ac.multiwindow_selection(
        "Please choose a subnet to put interface on",
        entries,
        max_choice_depth=1)

    if is_err:
        logger.info("No subnet was chosen")
        return

    chosen_ix = chosen_values[0]
    if chosen_ix == len(entries) - 1:
        logger.error("Creating a new subnet isn't yet supported")
        return

    subnet_id = subnet_ids[chosen_ix]
    subnet = subnets[subnet_id]
    logger.info("Creating {} interfaces in subnet {} from az {}".format(
                args.interface_nr, subnet['id'], subnet['az']))

    ac.clean_display()
    ac.print(f"Chose subnet at {entries[chosen_ix][0]} in az {subnet['az']}\n\n")

    interfaces_names = list()
    default_names = get_interfaces_default_names(subnet, interfaces,
                                                 args.interface_nr)
    for i in range(args.interface_nr):
        default_name = default_names[i]
        reply = ac.ask_question(f"Choose name for inteface {i} ({default_name}):")
        interfaces_names.append(reply or default_name)

    ac.print(f"\nCreating interfaces:\n")
    ac.print("\n".join(interfaces_names))

    if not yes_no_confirm():
        return

    logger.info("Creating intercaes: " + ", ".join(interfaces_names))


def configure_cli_arguments(cli_parser : argparse.ArgumentParser):
    """configure_cli_arguments configures the subparser for cli commands"""

    # subparsers = cli_parser.add_subparsers(
        # title='awsh helper cli commands',
        # help='''Command run in termianl. Tries to use client mode by default
# but falls back to using `aws ec2` cli if not supported''')
    cli_parser.add_argument(
        '-r',
        '--region',
        help='The region on which to operate',
        dest='region',
        required=True)

    cli_subcommands = cli_parser.add_subparsers(
        title="Available commands",
        help='Available cli commands')

    ## awsh cli create_interface
    add_interface = cli_subcommands.add_parser(
        "add_interface",
        help='Create interfaces')
    cli_parser.set_defaults(tool=create_intefaces)

    add_interface.add_argument(
        '-n',
        '--interface-number',
        help='How many interface to create',
        default=1,
        dest='interface_nr',
        type=int)

    mode_group = add_interface.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--client',
        help='Force running in client mode (requires a running awsh server)',
        dest='force_client_mode',
        action='store_true')

    mode_group.add_argument(
        '--aws-ec2',
        help='Force running aws ec2 cli for all operations',
        dest='force_aws_ec2_mode',
        action='store_true')
