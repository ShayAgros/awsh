#!/usr/bin/env python3

from typing import Any, List, Tuple
import boto3
import botocore.exceptions

from awsh_utils import get_os_by_ami_name

import json

prefrred_regions = [
   "us-east-1",
    # "eu-west-1"
        ]

os_to_username = {
            "Amazon Linux 2" : "ec2-user",
            "CentOS": "centos",
    }

RUNNING_STATE_CODE = 16
TERMINATED_STATE_CODE = 48

def ip_str_to_int(ip_str):
    ip_arr = ip_str.split('.')
    ip = 0

    for i in range(4):
        block = int(ip_arr[i])
        ip = ip + (block << (24 - i*8))

    return ip

def get_first_last_ips(cidr_block):
    ipstr, cidr_range = cidr_block.split('/')

    cidr_range = int(cidr_range)
    num_ips = (1 << (32 - cidr_range)) - 1

    start_ip = ip_str_to_int(ipstr)
    last_ip = start_ip + num_ips

    return start_ip, last_ip
    print("start ip is", hex(start_ip))
    print("last ip is", hex(last_ip))

def ip_int_to_str(ip):
    ip_arr = []
    for i in range(4):
        block = ip & 0xff
        ip_arr.insert(0, str(block))
        ip = ip >> 8

    return '.'.join(ip_arr)

def is_instance_running(cached_instance_entry):
    """Gets an instance object as returned from Aws.get_instance_in_region()
       and return if the instance is in a running state."""

    return cached_instance_entry['state']['Code'] == RUNNING_STATE_CODE

def _find_free_subnets(vpc, subnet_mask = 24, subnets_nr = 1):
    """This function is suboptimal as it only searches for subnets that start at
       A.B.C.0, which reduces the number of possible subnets we find. It was
       done this way to make it easier for humans to spot different subnets"""

    all_subnets = vpc.subnets.all()
    ip_range = [get_first_last_ips(subnet.cidr_block) for subnet in all_subnets]
    ip_range.sort(key = lambda ip_pair : ip_pair[0])

    vpc_first_ip, vpc_last_ip = get_first_last_ips(vpc.cidr_block)

    number_of_ips = (1 << (32 - subnet_mask)) - 1

    current_start_ip = vpc_first_ip
    returned_ips = []
    while current_start_ip + number_of_ips < vpc_last_ip and len(returned_ips) < subnets_nr:

        current_end_ip = current_start_ip + number_of_ips

        # remove existing subnets which end before the subnet we look for
        while len(ip_range) > 0 and ip_range[0][1] < current_start_ip:
            ip_range = ip_range[1:]

        if len(ip_range) == 0 or current_end_ip < ip_range[0][0]:
            returned_ips.append( (current_start_ip, current_end_ip) )

        current_start_ip = current_end_ip + 1

    if len(returned_ips) < subnets_nr:
        return

    ips_cidr = [ "{}/{}".format(ip_int_to_str(ip_pair[0]), subnet_mask) for ip_pair in returned_ips]
    return ips_cidr

def choose_from_list(qprompt, choices):
    # There's some issue with this module on the mac Python. Probably this whole
    # infra can be removed
    from PyInquirer import prompt

    options = [
            {
                'type'      : 'list',
                'name'      : 'question',
                'message'   : qprompt,
                'choices'   : choices,
            }
    ]

    answer = prompt(options)

    return answer['question']

class Aws:

    def __init__ (self):
        self.regions = dict()
        self.available_regions_list = None

    def get_instance_in_region(self, region, instance_id = None):
        """List instances in a given region, if instance_id is specified, query
        only this specific instance data"""

        ec2 = boto3.resource('ec2', region_name=region)
        if not instance_id:
            all_instances = ec2.instances.all()
        else:
            all_instances = ec2.instances.filter(
                        InstanceIds=[
                            instance_id,
                        ],
                    )

        has_running_instances = False

        ret_instances = list()
        for instance in all_instances:
            # don't return terminated instances
            if instance.state['Code'] == TERMINATED_STATE_CODE:
                continue
            if instance.state['Code'] == RUNNING_STATE_CODE:
                has_running_instances = True

            interfaces = list()
            for interface_attr in instance.network_interfaces_attribute:
                card_id_index = 0
                # on some instances the network card index is specified as well,
                # while on others it's not
                if 'NetworkCardIndex' in interface_attr['Attachment']:
                    card_id_index = interface_attr['Attachment']['NetworkCardIndex']

                interface = {
                    'id'                    : interface_attr['NetworkInterfaceId'],
                    'mac'                   : interface_attr['MacAddress'],
                    'private_ip'            : interface_attr['PrivateIpAddress'],
                    'subnet'                : interface_attr['SubnetId'],
                    'vpc'                   : interface_attr['VpcId'],
                    'security_group'        : interface_attr['Groups'],
                    'delete_on_termination' : interface_attr['Attachment']['DeleteOnTermination'],
                    'device_index'          : interface_attr['Attachment']['DeviceIndex'],
                    'card_id_index'         : card_id_index,
                    'description'           : interface_attr['Description'],
                }
                interfaces.append(interface)

            interfaces.sort(key=lambda k: k['card_id_index'])

            # Get 'Name' tag of the instance. 'tags' attribute might not be
            # defined
            instance_name = ''
            if instance.tags:
                for tag in instance.tags:
                    if tag['Key'] == 'Name':
                        instance_name = tag['Value']

            ret_instances.append({
                'name'              : instance_name,
                'id'                : instance.id,
                'ena_support'       : instance.ena_support,
                'state'             : instance.state,
                'architecture'      : instance.architecture,
                'ami_id'            : instance.image_id,
                'ami_name'          : instance.image.name,
                'distro'            : get_os_by_ami_name(instance.image.name),
                'key'               : instance.key_name,
                'public_dns'        : instance.public_dns_name,
                'public_ip'         : instance.public_ip_address,
                'placement'         : instance.placement,
                'az'                : instance.placement["AvailabilityZone"],
                'instance_type'     : instance.instance_type,
                'interfaces'        : interfaces,
                'num_interfaces'    : len(interfaces),
            })

        return ret_instances, has_running_instances

    def query_instances_in_regions(self, regions : list) -> Tuple[dict, Any]:
        instances = dict()
        has_running_instances = dict()

        for region in regions:
            try:
                instances[region], has_running_instances[region] = self.get_instance_in_region(region)
            except:
                print("Failed to query region", region)
                instances[region], has_running_instances[region] = list(), False

        return instances, has_running_instances

    def query_all_instances(self):
        """List instances in all regions available to user.
           Caution: this operation might take a while"""
        session = boto3.Session()

        if not self.available_regions_list:
            available_regions = session.get_available_regions('ec2')
            self.available_regions_list = list(available_regions)

        return self.query_instances_in_regions(self.available_regions_list)

    def quary_preferred_regions(self):
        return self.query_instances_in_regions(prefrred_regions)

    def print_online_instances(self):
        regions = self.regions
        available_regions = available_regions_list

        if not available_regions:
            session = boto3.Session()
            available_regions = session.get_available_regions('ec2')
            self.available_regions_list = available_regions

        for region in available_regions:
            print("Querying region: " + region)
            self.query_instances_in_regions([region])
            region_instances = regions[region]['instances']

            for instance_id in region_instances:
                instance = region_instances[instance_id]

                if instance["state"]["Code"] == RUNNING_STATE_CODE:
                    print("\"{tags}\" {id}: {key} {type} ({state}) dns: {dns}".format(
                        tags = instance["name"],
                        id = instance_id,
                        key = instance["key"],
                        type = instance["instance_type"],
                        state = instance["state"]["Name"],
                        dns = instance["public_dns"]))

    def get_subnet_all_pass_sec_group(self, subnet):
        """find a security group that passes all traffic,
           if it doesn't exist, create one"""

        all_pass_sec_group_name_params = {
                'Description' : 'Pass all traffic',
                'GroupName' : 'pass_all_traffic',
                }
        all_pass_sec_group_access_params = {
                'IpPermissions' : [
                    {
                        'IpProtocol' : '-1',
                        'IpRanges': [
                            {
                                'CidrIp': '0.0.0.0/0',
                                'Description': 'all_ipv4'
                                },
                            ],
                        'Ipv6Ranges': [
                            {
                                'CidrIpv6': '::/0',
                                'Description': 'all_ipv6'
                                },
                            ],
                        }
                    ]
                }

        vpc = subnet.vpc
        sec_groups = vpc.security_groups
        all_pass_sec_groups = sec_groups.filter(
                GroupNames=[
                    'pass_all_traffic'
                    ],
                )
        try:
            all_pass_sec_group = list(all_pass_sec_groups)[0]
        except:
            try:
                # the above command would fail if such group doesn't exist
                all_pass_sec_group = vpc.create_security_group(**all_pass_sec_group_name_params)
                # only authorise ingree. egress passes all traffic by default
                all_pass_sec_group.authorize_ingress(**all_pass_sec_group_access_params)
            except:
                all_pass_sec_group = None

        return all_pass_sec_group


    def create_ssh_icmp_enabled_sg_vpc(self, vpc):
        """Create a security group for a given VPC which allows to pass ssh
        traffic"""

        sec_group_name = 'ssh_icmp_traffic'
        sec_groups = vpc.security_groups
        sec_groups.filter( GroupNames=[ sec_group_name ],)
        if (not sec_groups):
           raise Exception("Security group already exists")

        sec_group_access_params = {
            'IpPermissions' : [
                {
                    'IpProtocol' : 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [
                        {
                            'CidrIp': '0.0.0.0/0',
                            'Description': 'all_ipv4'
                        },
                    ],
                    'Ipv6Ranges': [
                        {
                            'CidrIpv6': '::/0',
                            'Description': 'all_ipv6'
                        },
                    ],
                },
                {
                    'IpProtocol' : 'icmp',
                    'FromPort': -1,
                    'ToPort': -1,
                    'IpRanges': [
                        {
                            'CidrIp': '0.0.0.0/0',
                            'Description': 'all_ipv4'
                        },
                    ],
                    'Ipv6Ranges': [
                        {
                            'CidrIpv6': '::/0',
                            'Description': 'all_ipv6'
                        },
                    ],
                }
            ]
        }

        sec_group_name_params = {
                'Description' : 'Pass SSH and ICMP traffic',
                'GroupName' : sec_group_name,
                }

        # try:
        sec_group = vpc.create_security_group(**sec_group_name_params)
        sec_group.authorize_ingress(**sec_group_access_params)
        # except:
            # sec_group = None

        return sec_group

    def create_ssh_icmp_enabled_sg_region(self, region):
        ec2 = boto3.resource('ec2', region_name=region)

        for vpc in ec2.vpcs.all():
            self.create_ssh_icmp_enabled_sg_vpc(vpc)


    def create_ssh_icmp_enabled_sg_all_regions(self):
        session = boto3.Session()

        for region in list(session.get_available_regions('ec2')):
            print("Adding ssh icmp enabled sg in", region)
            try:
                self.create_ssh_icmp_enabled_sg_region(region)
            except:
                print("Failed")

    def parse_eni_metadata(self, interface):
        """Parse the metadata of ec2 interface object. This means extracting
        only the information needed for awsh functionality

        @interface: an interface object

        @returns dictionary of metadata"""

        interface_name = ''
        if interface.tag_set:
            for tag in interface.tag_set:
                if tag['Key'] == 'Name':
                    interface_name = tag['Value']

        attachment = interface.attachment
        delete_on_termination = attachment and attachment['DeleteOnTermination'] or False
        return {
                'name'                  : interface_name,
                'id'                    : interface.id,
                'az'                    : interface.availability_zone,
                'mac_address'           : interface.mac_address,
                'groups'                : interface.groups,
                'private_ip'            : interface.private_ip_address,
                'status'                : interface.status,
                'subnet'                : interface.subnet_id,
                'source_dest_check'     : interface.source_dest_check,
                'description'           : interface.description,
                'availability_zone'     : interface.availability_zone,
                'delete_on_termination' : delete_on_termination,
                }

    def create_interface(self, name, subnet, region = None):

        if isinstance(subnet, str):
            if not region:
                raise SystemExit("create_interface: passing subnet id argument requires to specify region")
            ec2 = boto3.resource('ec2', region_name=region)
            subnet = ec2.Subnet(subnet)
        else:
            region = subnet.availability_zone

        ec2 = boto3.resource('ec2', region_name=region)

        print("Creating interface", name)

        all_pass_sec_group = self.get_subnet_all_pass_sec_group(subnet)

        interface = subnet.create_network_interface(
                Description         = name,
                Groups              = [

                    all_pass_sec_group.id,
                    # 'sg-14057963' # default for eu-west-1, passes all traffic
                    # 'sg-2cdc3c72', # default for us-east-1, passes all traffic
                    # 'sg-025236cc42a95f96c', # all_traffic
                ],
                TagSpecifications   = [
                    {
                        'ResourceType'  : 'network-interface',
                        'Tags'          : [
                            {
                            'Key'   : 'Name',
                            'Value' : name,
                            }
                        ],
                    },
                ],
                )

        return self.parse_eni_metadata(interface)

    # TODO: add an option for this function to get a list of ENIs to detach.
    # This would save the server access
    def detach_private_enis(self, region, instance_id):
        ec2 = boto3.resource('ec2', region_name=region)
        instance = ec2.Instance(instance_id)

        enis_to_detach = list()
        for interface_attr in instance.network_interfaces_attribute:
            if not interface_attr['Attachment']['DeleteOnTermination']:
                enis_to_detach.append(interface_attr['NetworkInterfaceId'])

        if not len(enis_to_detach):
            return []

        for eni_id in enis_to_detach:
            eni = ec2.NetworkInterface(eni_id)
            eni.detach()

        instances, _ = self.get_instance_in_region(region, instance_id=instance_id)

        return enis_to_detach, instances[0]


    def _get_interface_in_region(self, region):
        ec2 = boto3.resource('ec2', region_name=region)
        all_interfaces = ec2.network_interfaces.all()

        ret_interfaces = dict()

        for interface in all_interfaces:
            ret_interfaces[interface.id] = self.parse_eni_metadata(interface)

        return ret_interfaces

    def query_interfaces_in_regions(self, regions):
        interfaces = dict()
        for region in regions:
            try:
                interfaces[region] = self._get_interface_in_region(region)
            except:
                print("Failed to query interfaces in region", region)
                interfaces[region] = dict()

        return interfaces

    def query_all_interfaces(self):
        """List interfaces in all regions available to user.
           Caution: this operation might take a while"""
        session = boto3.Session()

        if not self.available_regions_list:
            available_regions = session.get_available_regions('ec2')
            self.available_regions_list = list(available_regions)

        regions = self.query_interfaces_in_regions(self.available_regions_list)

        return regions

    def parse_subnet_metadata(self, subnet):
        """Parse the metadata of ec2 subnet object. This means extracting
        only the information needed for awsh functionality

        @subnet: an subnet object

        @returns dictionary of metadata"""

        subnet_name = ''
        if subnet.tags:
            for tag in subnet.tags:
                if tag['Key'] == 'Name':
                    subnet_name = tag['Value']

        return {
                'name'                  : subnet_name,
                'id'                    : subnet.id,
                'az'                    : subnet.availability_zone,
                'state'                 : subnet.state,
                'availability_zone'     : subnet.availability_zone,
                'default_for_az'        : subnet.default_for_az,
                }


    def _get_subnets_in_region(self, region):
        ec2 = boto3.resource('ec2', region_name=region)
        all_subnets = ec2.subnets.all()

        ret_subnets = dict()

        for subnet in all_subnets:
            ret_subnets[subnet.id] = self.parse_subnet_metadata(subnet)

        return ret_subnets

    def query_subnets_in_regions(self, regions):
        """Query all subnets in specified regions"""
        subnets = dict()
        for region in regions:
            try:
                subnets[region] = self._get_subnets_in_region(region)
            except:
                print("Failed to query subnets in region", region)
                subnets[region] = dict()

        return subnets

    def query_all_subnets(self):
        """List subnets in all regions available to user.
           Caution: this operation might take a while"""
        session = boto3.Session()

        if not self.available_regions_list:
            available_regions = session.get_available_regions('ec2')
            self.available_regions_list = list(available_regions)

        regions = self.query_subnets_in_regions(self.available_regions_list)

        return regions


    def _get_images_in_region(self, region):
        """Get Amazon's and private amis in a region
        @region: the region to query

        @returns a list of amis in that region"""
        ec2 = boto3.resource('ec2', region_name=region)
        all_amis = ec2.images.filter(
            Owners=[
                'self',
                'amazon',
            ]
        )

        # TODO: for one region it output 9298 lines of amis id. This is too much
        # information since you also need to store meta data for each one which would
        # multiply this output length.
        # You can filter by OS (linux / Windows / FBSD) for now, and maybe filter name
        # as well (so that you explicitly search for amis with the word al2 / ubuntu etc. in
        # them).
        #
        # For the near future, it'd be computationally cheaper if you query ami information
        # on the running ami alone (or even present a menu to the user asking what is the
        # distribution).
        #
        # without the ability to launch amis from script, querying all amis seems wasteful
        for ami in all_amis:
            print(ami)


    def query_images_in_regions(self, regions):
        """Get Amazon and private amis in specific regions
        @regions: the regions in which to query for amis

        @returns a dictionary with regions as keys and a list of amis as value"""
        images = dict()

        for region in regions:
                images[region] = self._get_images_in_region(region)

        return images

    def create_subnet(self, region, az, name, vpc = None):
        available_vpcs = 3
        ec2 = boto3.resource('ec2', region_name=region)

        if vpc:
            # supporting it might be trickier than what one might think
            # Creating an empty subnet requires to find an address range which
            # doesn't intersects with any other subnet. When we have several
            # LPCs this requires to search in subnets belonging to both
            print("Function doesn't support VPC argument")
            return
        else:
            vpc = list(ec2.vpcs.all())[0]
            print("VPC not specified, choosing first one: {}".format(vpc.id))

        subnets = _find_free_subnets(vpc)
        if not subnets:
            print("Failed to find 1 available subnet")
            return

        print("Gonna create this subnet:", subnets[0], "in az", az)
        print("subnets name would be", name)

        subnet = ec2.create_subnet(
                AvailabilityZone    = az,
                CidrBlock           = subnets[0],
                VpcId               = vpc.id,
                TagSpecifications   = [
                    {
                        'ResourceType'  : 'subnet',
                        'Tags'          : [
                            {
                            'Key'   : 'Name',
                            'Value' : name,
                            }
                        ],
                    },
                ],
        )

        return subnet

    def connect_eni_to_instance(self, region : str, instance_id : str, eni_id : str,
                                device_index : int, network_card_index = 0):

        ec2 = boto3.resource('ec2', region_name=region)

        # TODO: this all should be move to some CLI program. This file should be
        # backend only
        # if not instance_id:
            # running_instances, _ = self.get_instance_in_region(region)

            # instance_choices = list()
            # for instance in running_instances:
                # id   = instance['id']
                # name = instance['name']
                # size = instance['instance_type']

                # instance_choices.append('{} {} {}'.format(id, name, size))

            # if not instance_choices:
                # print("No running instances")
                # return

            # instance = choose_from_list('Choose instance to attach interface to', instance_choices)
            # instance_tuple = instance.split()

            # instance_id = instance_tuple[0]

        # if not eni_id:
            # running_instances, _ = self.get_instance_in_region(region)
            # instance_az = running_instances[instance_id]['placement']['AvailabilityZone']
            # print("You chose", instance_id, "from az", instance_az)


            # available_interfaces = ec2.network_interfaces.filter(
                        # Filters=[
                            # {
                                # 'Name': 'availability-zone',
                                # 'Values': [
                                    # instance_az,
                                # ]
                            # },
                            # {
                                # 'Name': 'status',
                                # 'Values': [
                                    # 'available',
                                # ]
                            # },
                        # ],
                # )

            # interfaces_choices = list()
            # for interface in available_interfaces:
                # eni_id = interface.id
                # eni_description = interface.description

                # interfaces_choices.append('{} {}'.format(eni_id, eni_description))

            # if not interfaces_choices:
                # print("No available interface, please create some")
                # return

            # interface = choose_from_list('Choose an interface to attach to the interface', interfaces_choices)
            # interface_tuple = interface.split()

            # eni_id = interface_tuple[0]

        eni = ec2.NetworkInterface(eni_id)
        eni.attach(
            DeviceIndex = device_index,
            InstanceId = instance_id,
            NetworkCardIndex = network_card_index
            )

        instances, _ = self.get_instance_in_region(region, instance_id=instance_id)

        return instances[0]

    def terminate_instance(self, instance_id, region):
        ec2 = boto3.resource('ec2', region_name=region)

        instance = ec2.Instance(instance_id)
        try:
            instance.terminate()
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                print("No client with instance id", instance_id, "exists in region", region)
            else:
                raise error

    def start_instance(self, instance_id, region, wait_to_start=False):
        ec2 = boto3.resource('ec2', region_name=region)

        instance = ec2.Instance(instance_id)
        try:
            # TODO: this function has use_cache option which isn't implemented.
            # After it would be please make it use the cache
            self.detach_private_enis(region=region, instance_id=instance_id)
            instance.start()
            if wait_to_start:
                # TODO: this can fail, need to check how to handle this error
                instance.wait_until_running()
                instances, _ = self.get_instance_in_region(region, instance_id=instance_id)
                return instances[0]
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                print("No client with instance id", instance_id, "exists in region", region)
            else:
                raise error

        return None

    def stop_instance(self, instance_id, region, wait_until_stop=False):
        ec2 = boto3.resource('ec2', region_name=region)

        instance = ec2.Instance(instance_id)
        try:
            instance.stop()
            if wait_until_stop:
                # TODO: this can fail, need to check how to handle this error
                instance.wait_until_stopped()
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                print("No client with instance id", instance_id, "exists in region", region)
            else:
                raise error

    def get_regions_full_name(self):
        """Get the long name of every region (e.g. Us West (Oregon)) for
        us-west-2.

        @returns a dictionary with region short names (e.g. us-west-2) as keys,
        and the region long name as value"""

        # the region doesn't really matter here, but it's a required parameter
        ssm = boto3.client('ssm', region_name='us-east-1')

        if not self.available_regions_list:
            session = boto3.Session()
            available_regions = session.get_available_regions('ec2')
            self.available_regions_list = list(available_regions)

        long_names = dict()
        requests = list()
        # taken from
        # https://www.sentiatechblog.com/retrieving-all-region-codes-and-names-with-boto3
        # maybe there's a more pythonic way. Couldn't find one
        for region in self.available_regions_list:
            req = f'/aws/service/global-infrastructure/regions/{region}/longName'
            requests.append(req)
            response = ssm.get_parameter(
                Name=f'/aws/service/global-infrastructure/regions/{region}/longName'
            )

            long_names[region] = response['Parameter']['Value']

        return long_names

def main():

    # ec2 = Aws()
    ec2 = boto3.resource('ec2', region_name="us-east-1")
    vpc = list(ec2.vpcs.all())[0]

    print(vpc.id)
    subnets = _find_free_subnets(vpc, 24, 16)
    print(subnets)

    # ec2.create_ssh_icmp_enabled_sg_all_regions()
    # ec2.create_ssh_icmp_enabled_sg_region("il-central-1")

    # subnets = ec2.query_subnets_in_regions(["eu-west-1"])
    # interfaces = ec2.query_interfaces_in_regions(["eu-west-1"])
    # print(json.dumps(subnets, indent=4))
    # print(ec2.get_regions_full_name())
    # ec2._get_images_in_region('us-west-2')
    # ec2.detach_private_enis('us-east-1', 'i-05f612a1327a46681')
    # subnet = ec2.create_subnet('eu-central-1', 'eu-central-1c', 'subnet-c-2')
    # res = ec2.create_interface('testing-c2-i1', subnet)
    # res = ec2.create_interface('testing-c2-i2', subnet)


    # subnet = "subnet-01b32812da965559e"
    # res = ec2.create_interface('testing-c1-i3', subnet, region='eu-west-1')
    # print(res)
    # ec2.create_interface('testing-d1-i3', subnet, region='us-west-2')
    # print(json.dumps(ec2._get_interface_in_region('us-west-2'), indent=4))

    # ec2.connect_eni_to_instance('eu-west-1')

    # print(json.dumps(ec2.start_instance('i-0ffff7e457b178ba8', 'us-west-2', wait_to_start=True), indent=4))
    # print(json.dumps(ec2.get_instance_in_region("eu-west-1"), indent = 4))
    # print(json.dumps(ec2.query_all_instances(), indent=4))
    # ec2.print_online_instances()

if __name__ == '__main__':
    main()
