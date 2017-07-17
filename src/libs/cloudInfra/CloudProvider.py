"""
Please refer to top-level LICENSE file for copyright information
"""

import time
import os
import logging
import boto
import boto.ec2
from fabric.api import (env, run, settings)

log = logging.getLogger(__name__)


class CloudProvider(object):
    """
    CloudProvider class is designed to encapsulate the functionality
    necessary to communicate with the cloud provider.
    """
    def connect(self):
        """
        The connect method will init a connection to the cloud provider.
        """
        raise RuntimeError("Implemented in child class")

    def create_instances(self, count, timeout_sec=300):
        """
        The create_instances method will request the specified number of
        instances/VMs from the cloud provider.
        :param count:
        :param timeout_sec:
        :return: list of virtualInstances
        """
        raise RuntimeError("Implemented in child class")

    def destroy_all_instances(self):
        """
        The destroy_all_instances method will request that all the
        instances allocated via create_instances are destroyed.
        :return:
        """
        raise RuntimeError("Implemented in child class")


class CloudProviderAWS(CloudProvider):
    """
    CloudProviderAWS class, contains functionality to specifically
    work with AWS instances.
    """

    # pylint: disable=too-many-instance-attributes
    # Lots of little pieces of information here, easier to track.
    def __init__(self,
                 ec2_instance_image='ami-2afbde4a',
                 ec2_instance_user_name='ubuntu',
                 ec2_instance_type='t2.micro',
                 ec2_security_group='botoTestSecGrp',
                 ec2_security_group_desc='Security group for boto run',
                 ec2_region=None,
                 ec2_aws_key=None,
                 ec2_aws_secret_key=None,
                 ec2_key_pair_name=None,
                 ec2_key_pair_file_path=None):
        self._ec2_instance_image = ec2_instance_image
        self._ec2_instance_user_name = ec2_instance_user_name
        self._ec2_instance_type = ec2_instance_type
        self._ec2_security_group = ec2_security_group
        self._ec2_security_group_desc = ec2_security_group_desc
        self._ec2_key_pair_name = ec2_key_pair_name

        self._ec2 = None
        self._ec2_reservation = None
        self._ec2_instances = None
        self._ec2_key_file = ec2_key_pair_file_path
        self._ec2_region = ec2_region
        self._ec2_aws_key = ec2_aws_key
        self._ec2_aws_secret_key = ec2_aws_secret_key

    def connect(self):
        self._ec2 = boto.ec2.connect_to_region(
                        self._ec2_region,
                        aws_access_key_id=self._ec2_aws_key,
                        aws_secret_access_key=self._ec2_aws_secret_key)
        if self._ec2 is None:
            logging.error('Could not connect to ec2 region: %s',
                          self._ec2_region)
            raise Exception

        if not self._ec2.get_key_pair(self._ec2_key_pair_name):
            log.error("Could not find keypair: %s", self._ec2_key_pair_name)
            raise Exception('Keypair not found on AWS')
        if not os.path.exists(self._ec2_key_file):
            log.error('Could not find keypair file: %s', self._ec2_key_file)
            raise Exception('Keypair file not found')

        # Setup security group if necessary
        try:
            sec_groups = self._ec2.get_all_security_groups(
                [self._ec2_security_group])
            if len(sec_groups) != 1:
                logging.error('Expected 1 group, found more then one:%s',
                              str(sec_groups))
                raise Exception
            sec_groups.pop()
        except boto.exception.EC2ResponseError:
            # Honestly, we should parse the xml data here in the exception
            # to see that this was actually due to the security group not being
            # found.

            # Create security group
            log.info('Security group not found, attempting to create')
            sec_group = \
                self._ec2.create_security_group(self._ec2_security_group,
                                                self._ec2_security_group_desc)
            # Open up port 22 for ssh access
            sec_group.authorize(ip_protocol='tcp',
                                from_port=22,
                                to_port=22,
                                cidr_ip='0.0.0.0/0')
            log.info('Done creating security group: %s', sec_group.name)

    def create_instances(self, count, timeout_sec=300):
        self._ec2_reservation = \
            self._ec2.run_instances(self._ec2_instance_image,
                                    instance_type=self._ec2_instance_type,
                                    security_groups=[self._ec2_security_group],
                                    key_name=self._ec2_key_pair_name,
                                    min_count=count,
                                    max_count=count)

        self._ec2_instances = self._ec2_reservation.instances

        # Wait for the instances to fully init. run local command and
        # get output
        if not self._wait_for_instance_state(300, 'running'):
            self.destroy_all_instances()
            raise Exception
        log.info('Instances have successfully started')
        virtual_instances = []
        for instance in self._ec2_instances:
            virtual_instances.append(
                VirtualInstanceAWS(instance=instance,
                                   key_file=self._ec2_key_file,
                                   login_name=self._ec2_instance_user_name))
        return virtual_instances

    def destroy_all_instances(self):
        instance_ids = []
        for instance in self._ec2_instances:
            instance_ids.append(instance.id)
        self._ec2.terminate_instances(instance_ids=instance_ids)
        if not self._wait_for_instance_state(300, 'terminated'):
            raise Exception

    def _wait_for_instance_state(self, timeout_sec, state):
        timeout = time.time() + timeout_sec
        all_match_state = False
        while time.time() < timeout and all_match_state is False:
            all_match_state = True
            for instance in self._ec2_reservation.instances:
                try:
                    instance.update()
                    log.info('Found instance with state: %s', instance.state)
                    if instance.state != state:
                        all_match_state = False
                except Exception:
                    # Sometimes AWS doesn't recognize it's own instances for a
                    # bit, ignore, and keep trying.
                    all_match_state = False

            log.info('Waiting for instances to match state: %s', state)
            if all_match_state is False:
                time.sleep(30)
        if time.time() >= timeout:
            log.error('Timed out waiting for instances to match state: %s',
                       state)
            return False
        log.info('All instances now match state: %s ', state)
        return True


class VirtualInstance(object):
    """
    The VirtualInstance class encapsulates functionality that deals with
    the virtual instance. (Mostly involving GOS (Guest Operating System)
    operations.
    """
    def __init__(self, instance=None, key_file=None, login_name=None):
        self._instance = instance
        self._key_file = key_file
        self._login_name = login_name

    def get_instance_id(self):
        raise RuntimeError("Implemented in child class")

    def get_instance_ip(self):
        raise RuntimeError("Implemented in child class")

    def wait_for_gos_to_respond(self, timeout_sec=300):
        timeout = time.time() + timeout_sec
        gos_responds = False
        while timeout > time.time() and gos_responds is False:
            try:
                self.run_command_on_gos('echo hello', 120)
                gos_responds = True
            except Exception:
                log.exception("Got exception while waiting for GOS to respond")
                log.info('Waiting for GOS to respond')
                time.sleep(10)

    def run_command_on_gos(self, command, timeout_sec=120):
        raise RuntimeError("Implemented in child class")


class VirtualInstanceAWS(VirtualInstance):
    """
    The VirtualInstanceAWS class encapsulates functionality specific
    to AWS instances.
    """
    def __init__(self, instance, key_file, login_name):
        super(self.__class__, self).__init__(instance=instance,
                                             key_file=key_file,
                                             login_name=login_name)
        if not (login_name and key_file):
            log.error("Need login name + keyfile for AWS connections")
            raise RuntimeError("Missing creds for AWS")
        env.use_ssh_config = False
        env.user = self._login_name
        env.key_filename = self._key_file
        env.password = ""
        env.disable_known_hosts=True # AWS instances are transitory
        env.warn_only = True

    def get_instance_id(self):
        return self._instance.id

    def get_instance_ip(self):
        return self._instance.ip_address

    def run_command_on_gos(self, command, timeout_sec=120):
        log.info("Running command: %s", command)
        with settings(host_string=self.get_instance_ip()):
            result = run(command, timeout=timeout_sec)
            if result.return_code != 0:
                log.error("Error stdout:%s", result.stdout)
                log.error("Error stderr:%s", result.stderr)
                raise RuntimeError('Error found while running cmd')
            return result.stdout
