#!/usr/bin/env python3

import argparse
import logging
import coloredlogs
import sys

from awsh_server import start_server
from awsh_utils import get_entry_at_index
from awsh_client import get_current_state
from awsh_cli import configure_cli_arguments

def parse_client_arguments(args):

    instance_id = None
    if args.instance_ix:
        entry = get_entry_at_index(args.instance_ix)
        if entry is None:
            # print error
            return

    if instance_id is None:
        print("Please provide an instance identifier")
        return

    regions = get_current_state()

    pass


def main():

    log_levels = ["INFO", "DEBUG"]

    parser = argparse.ArgumentParser(description='AWS helper')
    subparsers = parser.add_subparsers(
        title='Commands',
        help='Supported sub-commands')

    parser.set_defaults(tool='')

    parser.add_argument('--log', help='log level', dest='log_level',
                        choices=log_levels, default=logging.INFO)

    # server mode
    server_mode = subparsers.add_parser(
        "server",
        aliases=['s'],
        help='Run AWS helper in background (queries AWS state continuously')

    server_mode.set_defaults(tool=start_server)

    # awsh cli [command]
    cli_mode = subparsers.add_parser(
        "cli",
        aliases=['c'],
        help='''Command run in termianl. Tries to use client mode by default
but falls back to using `aws ec2` cli if not supported''')
    configure_cli_arguments(cli_mode)


    # awsh client [command]
    client_mode = subparsers.add_parser(
        "client",
        help='Run AWS helper client command')

    client_mode.set_defaults(tool=parse_client_arguments)
    client_mode.add_argument(
        '--instance-index',
        help='Specify instance by device index',
        dest='instance_ix',
        type=int)
    client_mode.add_argument(
        '--print-info',
        help='Print instance info',
        dest='print_info',
        action='store_true',
        default=False)

    args = parser.parse_args()

    coloredlogs.DEFAULT_LOG_FORMAT = '%(asctime)s %(name)-20s %(levelname)s %(message)s'
    coloredlogs.install(level=args.log_level, stream=sys.stdout)

    if args.tool:
        args.tool(args)
    else:
        print("Please choose a subcommand")


if __name__ == '__main__':
    main()
