#!/usr/bin/env python
"""
Please refer to top-level LICENSE file for copyright information
"""


import time
import os
import re
import threading
import argparse
import logging
import json
import boto
import boto.ec2
from boto.s3.connection import S3Connection
from fabric.api import (env, run, settings)


logging.basicConfig(level=logging.INFO)
log = logging.getLogger('AwsRunner')

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
            sec_group = sec_groups.pop()
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
                    log.info('Found instance with state: %s',
                                 instance.state)
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


class VirtualStorage(object):
    """
    VirtualStorage class encapsulates the virtual storage functionality.
    """
    def connect(self):
        """
        The connect method will init a connection to the storage system.
        :return:
        """
        raise RuntimeError("Implemented in child class")

    def bucket_exists(self, bucket_name):
        """
        The bucket_exists method is used to find if a specified bucket
        already exists
        :param bucket_name: string containing the name of a bucket.
        :return: True if the bucket exists, False otherwise.
        """
        raise RuntimeError("Implemented in child class")

    def create_bucket(self, bucket_name):
        """
        The create_bucket method will create the specified bucket on the
        storage system.
        :param bucket_name: string containing the name of a new bucket.
        :return:
        """
        raise RuntimeError("Implemented in child class")

    def delete_bucket(self, bucket_name):
        """
        The delete_bucket method will delete an existing bucket on the storage
        The delete_bucket method will delete an existing bucket on the storage
        system.
        :param bucket_name: string containing the name of a bucket.
        :return:
        """
        raise RuntimeError("Implemented in child class")

    def erase_bucket(self, bucket_name):
        """
        The erase_bucket method will delete the contents of an existing bucket.
        :param bucket_name: string containing the name of a bucket.
        :return:
        """
        raise RuntimeError("Implemented in child class")


class VirtualStorageS3(VirtualStorage):
    """
    VirtualStorageS3 class encapsulates the virtual storage functionality
    specific to and AWS S3 object store.
    """
    def __init__(self, aws_key=None, aws_secret_key=None,):
        self._aws_key = aws_key
        self._aws_secret_key = aws_secret_key

        self._s3_store_connect = None
        self._s3_bucket = None

    def connect(self):
        self._s3_store_connect = S3Connection(self._aws_key,
                                              self._aws_secret_key)

    def bucket_exists(self, bucket_name):
        if self._s3_store_connect.lookup(bucket_name) is not None:
            return True
        else:
            return False

    def create_bucket(self, bucket_name):
        self._s3_store_connect.create_bucket(bucket_name)

    def _get_bucket(self, bucket_name):
        return self._s3_store_connect.get_bucket(bucket_name)

    def delete_bucket(self, bucket_name):
        self._s3_store_connect.delete_bucket(self._get_bucket(bucket_name))

    def erase_bucket(self, bucket_name):
        bucket = self._s3_store_connect.get_bucket(bucket_name)
        for key in bucket.list():
            key.delete()


class TestInstance(object):
    """
    TestInstance class encapsulates the test logic.  If other tests are needed
    they can extend this class and override methods as necessary.
    """
    def __init__(self,
                 virtual_instance,
                 bucket_name,
                 bucket_folder='/mnt/bucket',
                 aws_key=None,
                 aws_sec_key=None):
        self._s3_fs_package = 's3fs-fuse'
        self._s3_fs_server = 'https://github.com/s3fs-fuse/s3fs-fuse.git'
        self._vinstance = virtual_instance
        self._bucket_folder = bucket_folder
        self._aws_key = aws_key
        self._aws_sec_key = aws_sec_key
        self._s3_bucket_name = bucket_name
        self._unique_dir = \
            self._bucket_folder + '/test_' + self._vinstance.get_instance_id()

    def get_virtual_jnstance(self):
        """
        The get_virtual_instance method will return the virtual instance object
        :return: virtual instance object
        """
        return self._vinstance

    def setup_environment(self):
        """
        The setup_environment method will pre-setup the test environment
        before the test executes.  Installs programs, packages, etc.
        :return:
        """

        # Make sure the OS is responding
        self._vinstance.wait_for_gos_to_respond()

        # install OS packages.
        apt_get_cmd = 'DEBIAN_FRONTEND=noninteractive sudo apt-get -y '

        pkg_list = 'build-essential libfuse-dev' \
                  ' libxml2-dev mime-support automake autotools-dev' \
                  ' g++ git libcurl4-gnutls-dev libssl-dev libxml2-dev' \
                  ' make pkg-config'
        self._vinstance.run_command_on_gos(apt_get_cmd + 'update', 300)
        self._vinstance.run_command_on_gos(apt_get_cmd + 'install ' +
                                           pkg_list, 300)

        # Install s3fs
        self._vinstance.run_command_on_gos('git clone %s' % self._s3_fs_server)
        self._vinstance.run_command_on_gos('cd %s; ./autogen.sh' %
                                            self._s3_fs_package, 120)
        self._vinstance.run_command_on_gos('cd ' + self._s3_fs_package +
                                           '; ./configure --prefix=/usr', 120)
        self._vinstance.run_command_on_gos('cd ' + self._s3_fs_package +
                                           '; make', 300)
        self._vinstance.run_command_on_gos('cd ' + self._s3_fs_package +
                                           '; sudo make install', 300)

        # Check that s3fs is responsive
        self._vinstance.run_command_on_gos('/usr/bin/s3fs -h', 120)

        # Create the bucket directory for later mounting
        self._vinstance.run_command_on_gos('sudo mkdir -p ' +
                                           self._bucket_folder)
        self._vinstance.run_command_on_gos('sudo chmod 777 ' +
                                           self._bucket_folder)

    def pre_test_setup(self):
        """
        The pre_test_setup method will prepare the testing environment,
        mounting shares, etc.
        :return:
        """
        # Mount the bucket
        self._vinstance.run_command_on_gos(
            'AWSACCESSKEYID=' + self._aws_key +
            ' AWSSECRETACCESSKEY=' + self._aws_sec_key +
            ' s3fs ' + self._s3_bucket_name + ': ' +
            self._bucket_folder)
        # Create a subdir for the files.
        self._vinstance.run_command_on_gos(
            'mkdir -p ' + self._bucket_folder + '/test_' +
            self._vinstance.get_instance_id())

    def execute_test(self, file_type='zero'):
        """
        The execute_test method will trigger the actual test and record
        results.
        :param file_type: file_type to use for the operation(zero/random)
        :return:
        """
        if file_type == 'zero':
            create_command = 'time for i in `seq 1 100`;' \
                            ' do dd if=/dev/zero of=' + self._unique_dir +\
                            '/test$i bs=1024 count=4; done'
        elif file_type == 'random':
            create_command = 'time for i in `seq 1 100`;' \
                            ' do dd if=/dev/urandom of=' + self._unique_dir +\
                            '/test$i bs=1024 count=4; done'
        else:
            log.error('Unknown file type specified, expected zero/random')
            raise Exception()
        read_command = 'time for i in `seq 1 100`; do cat ' + self._unique_dir +\
                      '/test$i >> /dev/null; done'
        delete_command = 'time for i in `seq 1 100`; do rm ' +\
                        self._unique_dir + '/test$i; done'
        try:
            create_output = self._vinstance.run_command_on_gos(create_command,
                                                               600)
        except:
            log.error('Error while running file create command')
            create_output = ""
        try:
            read_output = self._vinstance.run_command_on_gos(read_command,
                                                             600)
        except Exception:
            log.error('Error while running file read command')
            read_output = ""
        try:
            delete_output = self._vinstance.run_command_on_gos(delete_command,
                                                               600)
        except Exception:
            delete_output = ""
            log.error('Error while running file delete command')
        return self.parse_output(create_output, read_output, delete_output)

    def _get_time_ms(self, minutes, seconds, millisec):
        time_ms = 0
        time_ms += int(minutes) * 60 * 1000
        time_ms += int(seconds) * 1000
        time_ms += int(millisec)
        return time_ms

    def parse_output(self, create_output, read_output, delete_output):
        """
        The parse_output method will parse through the given outputs and
        return a RunResult object containing the data for the test.
        :param create_output: output from create operations.
        :param read_output:  output from read operations.
        :param delete_output: output from delete operations.
        :return: RunResult object
        """
        run_result = RunResult(self._vinstance.get_instance_id)

        time_pattern = r'real\s+(\d+)m(\d+)\.(\d+)s'
        match = re.search(time_pattern, create_output)
        if match:
            run_result.set_file_create_status(True)
            run_result.set_file_create_time_ms(
                self._get_time_ms(match.group(1),
                                  match.group(2),
                                  match.group(3)))
        else:
            run_result.set_file_create_status(False)

        match = re.search(time_pattern, read_output)
        if match:
            run_result.set_file_read_status(True)
            run_result.set_file_read_time_ms(self._get_time_ms(match.group(1),
                                                               match.group(2),
                                                               match.group(3)))
        else:
            run_result.set_file_read_status(False)

        match = re.search(time_pattern, delete_output)
        if match:
            run_result.set_file_delete_status(True)
            run_result.set_file_delete_time_ms(self._get_time_ms(match.group(1),
                                                                 match.group(2),
                                                                 match.group(3)))
        else:
            run_result.set_file_delete_status(False)
        return run_result

    def cleanup(self):
        """
        The cleanup method will remove created files, and unmount the share.
        :return:
        """
        self._vinstance.run_command_on_gos('rm -rf ' +
                                           self._bucket_folder + '/*')
        self._vinstance.run_command_on_gos('sudo umount ' +
                                           self._bucket_folder)


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
        super(VirtualInstanceAWS, self).__init__(instance=instance,
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


class RunAverages(object):
    """
    RunAverages class to manages the averaged data for the tests being run.
    """
    def __init__(self, run_result_list, run_id):
        self._total_create_pass = 0
        self._total_create_fail = 0
        self._total_create_time_ms = 0
        self._average_create_time_ms = 0
        self._total_read_pass = 0
        self._total_read_fail = 0
        self._total_read_time_ms = 0
        self._average_read_time_ms = 0
        self._total_delete_pass = 0
        self._total_delete_fail = 0
        self._average_delete_time_ms = 0
        self._total_delete_time_ms = 0

        self._run_id = run_id
        for report in run_result_list:
            if report.get_file_create_status():
                self._total_create_pass += 1
                self._total_create_time_ms += report.get_file_create_time_ms()
            else:
                self._total_create_fail += 1
            if report.get_file_read_status():
                self._total_read_pass += 1
                self._total_read_time_ms += report.get_file_read_time_ms()
            else:
                self._total_read_fail += 1
            if report.get_file_delete_status():
                self._total_delete_pass += 1
                self._total_delete_time_ms += report.get_file_delete_time_ms()
            else:
                self._total_delete_fail += 1
        if self._total_create_pass == 0:
            self._average_create_time_ms = -1
        else:
            self._average_create_time_ms = \
                self._total_create_time_ms / self._total_create_pass
        if self._total_read_pass == 0:
            self._average_create_time_ms = -1
        else:
            self._average_read_time_ms = \
                self._total_read_time_ms / self._total_read_pass
        if self._total_delete_pass == 0:
            self._average_delete_time_ms = -1
        else:
            self._average_delete_time_ms = \
                self._total_delete_time_ms / self._total_delete_pass

    def get_avg_create_time_ms(self):
        return self._average_create_time_ms

    def get_avg_read_time_ms(self):
        return self._average_read_time_ms

    def get_avg_delete_time_ms(self):
        return self._average_delete_time_ms

    def get_run_id(self):
        return self._run_id


class RunResult(object):
    """
    The RunResult class deals with the per-instance per-run data.
    """
    def __init__(self, resultId):
        self._id = resultId
        self._file_create_time_ms = 0
        self._file_create_status = False
        self._file_read_time_ms = 0
        self._file_read_status = False
        self._file_delete_time_ms = 0
        self._file_delete_status = False

    def set_file_create_status(self, status):
        self._file_create_status = status

    def get_file_create_status(self):
        return self._file_create_status

    def get_file_create_time_ms(self):
        return self._file_create_time_ms

    def set_file_create_time_ms(self, time_ms):
        self._file_create_time_ms = time_ms

    def set_file_read_status(self, status):
        self._file_read_status = status

    def get_file_read_status(self):
        return self._file_read_status

    def get_file_read_time_ms(self):
        return self._file_read_time_ms

    def set_file_read_time_ms(self, time_ms):
        self._file_read_time_ms = time_ms

    def set_file_delete_status(self, status):
        self._file_delete_status = status

    def get_file_delete_status(self):
        return self._file_delete_status

    def get_file_delete_time_ms(self):
        return self._file_delete_time_ms

    def set_file_delete_time_ms(self, time_ms):
        self._file_delete_time_ms = time_ms

    def get_id(self):
        return self._id


class ThreadWithError(threading.Thread):
    """
    Quick extended thread class to help us capture/report errors
    """
    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)
        self.error = False

    def run(self):
        self.error = False
        try:
            super(self.__class__, self).run()
        except Exception as err:
            log.error("Hit error in thread:%s", err.message)
            self.error = True

    def has_error(self):
        return self.error

# Quick global data structure for all threads to report into.
test_per_run_results = []


def report_results(list_of_results, outfile=None):
    results = []
    for run_result in list_of_results:
        result = {}
        result['RunId'] = str(run_result.get_run_id())
        result['AvgCreateTimeMs'] = str(run_result.get_avg_create_time_ms())
        result['AvgReadTimeMs'] = str(run_result.get_avg_read_time_ms())
        result['AvgDelTimeMs'] = str(run_result.get_avg_delete_time_ms())
        results.append(result)
    log.info(json.dumps(results))
    if outfile:
        with open(outfile, 'w') as out_file:
            out_file.write(json.dumps(results))
            out_file.close()


def general_test_prep(test_object):
    test_object.setup_environment()


def pre_test_setup(test_object):
    test_object.pre_test_setup()


def run_test(test_object, lock_obj):
    # result = test_object.execute_test('random')
    result = test_object.execute_test()
    with lock_obj:
        test_per_run_results.append(result)


def main():
    # Parse the command line for required parameters
    parser = argparse.ArgumentParser()
    parser.add_argument('--clients', type=int,
                        help='Number of instances to run')
    parser.add_argument('--bucket', help='Name of the bucket to create')
    parser.add_argument('--key', help='access key')
    parser.add_argument('--secretkey', help='secret key')
    parser.add_argument('--keypairname', help='key pair name'),
    parser.add_argument('--keypairfile', help='path to .pem file created with'
                                            'key pair')
    parser.add_argument('--region', help='region where instance will run')
    parser.add_argument('--outfile', help='file to output json results to')
    args = parser.parse_args()

    if args.clients <= 0:
        log.error('Error, number of clients must be > 0')
        raise Exception("Invalid number of clients")

    if args.bucket is None:
        log.error('Bucket not specified')
        raise Exception("Bucket not specified")

    # Check that the required credentials are found by boto
    #region_name = boto.config.get('Boto', 'ec2_region_name')
    if args.region is None:
        log.warn('Region not specified, using default')
        raise Exception("Region name not specified")
    #aws_key_id = boto.config.get('Credentials', 'aws_access_key_id')
    if args.key is None:
        log.error('Error, access key not specified')
        raise Exception("access key not specified")
    # aws_sec_key = boto.config.get('Credentials', 'aws_secret_access_key')
    if args.secretkey is None:
        log.error('Error, secret key not specified')
        raise Exception("secret key not specified")

    if args.keypairname is None:
        log.error('Error, keypair name not specified')
        raise Exception("keypair not specified")

    if args.keypairfile is None:
        log.error('Error, keypair file path not specified')
        raise Exception("keypair file not specified")
    if not os.path.isfile(args.keypairfile):
        raise Exception("keypair file not found:" + args.keypairfile)

    # Setup cloud provider connection (AWS)
    cloud_provider = CloudProviderAWS(ec2_region=args.region,
                                      ec2_aws_key=args.key,
                                      ec2_aws_secret_key=args.secretkey,
                                      ec2_key_pair_name=args.keypairname,
                                      ec2_key_pair_file_path=args.keypairfile)
    cloud_provider.connect()

    # Storage stuff.
    storage = VirtualStorageS3(aws_key=args.key, aws_secret_key=args.secretkey)
    storage.connect()

    if storage.bucket_exists(args.bucket):
        storage.erase_bucket(args.bucket)
        storage.delete_bucket(args.bucket)

    storage.create_bucket(args.bucket)

    # Setup all the GOS in parallel
    virtual_instances = cloud_provider.create_instances(args.clients)
    #testPerRunResult = []
    test_object_list = []
    thread_list = []
    test_run_averages = []

    try:
        lockobj = threading.Lock()
        # Create all possible instances for this test,
        # and prepare as much as possible
        # before tests will begin.
        for vinstance in virtual_instances:
            test_object = TestInstance(vinstance, args.bucket,
                                       '/mnt/bucket', args.key, args.secretkey)
            test_object_list.append(test_object)
            t = ThreadWithError(target=general_test_prep, args=(test_object,))
            thread_list.append(t)
            t.start()

        for t in thread_list:
            t.join(900)
            if t.is_alive():
                raise RuntimeError('Timed out during system prep')
            if t.has_error():
                raise RuntimeError('Error during system prep')

        # Run the tests. (1st client, 1st + 2nd client, 1+2+3,...)
        # Gathers averages for all numbers of clients.
        for i in range(1, args.clients + 1):
            # Prepare the selected instances to run the test.
            thread_list = []
            for j in range(0, i):
                t = ThreadWithError(target=pre_test_setup,
                                    args=(test_object_list[j],))
                thread_list.append(t)
                t.start()
            for t in thread_list:
                t.join(900)
                if t.is_alive():
                    raise RuntimeError('Timed out during test prep')
                if t.has_error():
                    raise RuntimeError('Error during test prep')

            # Actually trigger the benchmark test.
            thread_list = []
            for j in range(0, i):
                t = ThreadWithError(target=run_test,
                                    args=(test_object_list[j], lockobj,))
                thread_list.append(t)
                t.start()
            for t in thread_list:
                t.join(900)
                if t.is_alive():
                    raise RuntimeError('Timed out during test execution')
                if t.has_error():
                    raise RuntimeError('Error during test execution')

            # Cleanup, and prepare for the next test.
            for j in range(0, i):
                test_object_list[j].cleanup()

            # Store the benchmark information (averages of instances run).
            test_run_averages.append(RunAverages(test_per_run_results, i))
    except Exception:
        log.exception('Error while attempting to run test,'
                          ' attempting to clean up')

    # Cleanup the testbed
    cloud_provider.destroy_all_instances()
    storage.delete_bucket(args.bucket)

    # Output a report of the test runs.
    report_results(test_run_averages, outfile=args.outfile)


if __name__ == '__main__':
    main()
