#!/usr/bin/env python3

import boto3
import argparse
import logging, coloredlogs, sys

from awsh_server import start_server

def main():

    log_levels = ["INFO", "DEBUG"]

    parser = argparse.ArgumentParser(description='AWS helper')
    subparsers = parser.add_subparsers(title='Commands', help='Supported sub-commands')

    parser.set_defaults(tool='')

    parser.add_argument('--log', help='log level', dest='log_level', choices=log_levels, default=logging.INFO)

    # server mode
    server_mode = subparsers.add_parser("server", aliases=['s'], help='Run AWS helper in background (queries AWS state continuously')
    server_mode.set_defaults(tool=start_server)

    args = parser.parse_args()

    coloredlogs.DEFAULT_LOG_FORMAT = '%(asctime)s %(name)-20s %(levelname)s %(message)s'
    coloredlogs.install(level=args.log_level, stream=sys.stdout)

    if args.tool:
        args.tool(args)
    else:
        print("Please choose a subcommand")

if __name__ == '__main__':
    main()

