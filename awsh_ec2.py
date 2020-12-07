#!/usr/bin/env python3

import boto3

class Aws:
    def __init__ (self):
        self.profile = "default"

    def list_instance_in_region(self, region):
        """List instances in a given region"""

        # ec2 = self.client
        ec2 = boto3.resource('ec2', region_name=region)
        all_instances = ec2.instances.all()

        print("Listing instances in " + region)

        for instance in all_instances:
            print("{id}: {key} {type} ({state})".format(
                id = instance.instance_id,
                key = instance.key_name,
                type = instance.instance_type,
                state = instance.state["Name"]))

    def list_all_instances(self):
        """List instances in all regions available to user.
           Caution: this operation might take a while"""
        session = boto3.Session()
        available_regions = session.get_available_regions('ec2')
        for region in available_regions:
            self.list_instance_in_region(region)

ec2 = Aws()

# ec2.list_instances(region="eu-west-1")
ec2.list_all_instances()
