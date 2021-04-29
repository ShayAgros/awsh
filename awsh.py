#!/usr/bin/env python3

import boto3
import argparse

from awsh_server import start_server

def main():
    parser = argparse.ArgumentParser(description='AWS helper')
    subparsers = parser.add_subparsers(title='Commands', help='Supported sub-commands')

    parser.set_defaults(tool='')

    # server mode
    server_mode = subparsers.add_parser("server", aliases=['s'], help='Run AWS helper in background (queries AWS state continuously')
    server_mode.set_defaults(tool=start_server)

    args = parser.parse_args()

    if args.tool:
        args.tool(args)
    else:
        print("Please choose a subcommand")

if __name__ == '__main__':
    main()

