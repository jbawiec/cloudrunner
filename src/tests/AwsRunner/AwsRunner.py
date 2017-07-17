#!/usr/bin/env python
"""
Please refer to top-level LICENSE file for copyright information
"""

import argparse
import json
import logging
import os
import re

from src.libs.cloudInfra import CloudProvider
from src.libs.cloudInfra import CloudStorage
from src.libs.testFramework import classicTest


logging.basicConfig(level=logging.INFO)
log = logging.getLogger('AwsRunner')


class Test(classicTest.TestInstance):
    """
    Test class encapsulates the test logic.  If other tests are needed
    they can extend this class and override methods as necessary.
    """
    def __init__(self,
                 virtual_instance,
                 bucket_name,
                 bucket_folder='/mnt/bucket',
                 aws_key=None,
                 aws_sec_key=None):
        super(self.__class__, self).__init__(virtual_instance=virtual_instance)

        self._s3_fs_package = 's3fs-fuse'
        self._s3_fs_server = 'https://github.com/s3fs-fuse/s3fs-fuse.git'
        self._vinstance = virtual_instance
        self._bucket_folder = bucket_folder
        self._aws_key = aws_key
        self._aws_sec_key = aws_sec_key
        self._s3_bucket_name = bucket_name
        self._unique_dir = \
            self._bucket_folder + '/test_' + self._vinstance.get_instance_id()

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
        super(self.__class__, self).pre_test_setup()

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
        super(self.__class__, self).execute_test()
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
        read_command = 'time for i in `seq 1 100`; do cat ' +\
                       self._unique_dir + '/test$i >> /dev/null; done'
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
            run_result.set_file_delete_time_ms(
                self._get_time_ms(match.group(1),
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
        super(self.__class__, self).cleanup()
        self._vinstance.run_command_on_gos('rm -rf ' +
                                           self._bucket_folder + '/*')
        self._vinstance.run_command_on_gos('sudo umount ' +
                                           self._bucket_folder)


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
    if args.region is None:
        log.warn('Region not specified, using default')
        raise Exception("Region name not specified")
    if args.key is None:
        log.error('Error, access key not specified')
        raise Exception("access key not specified")
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
    cloud_provider = CloudProvider.CloudProviderAWS(
                        ec2_region=args.region,
                        ec2_aws_key=args.key,
                        ec2_aws_secret_key=args.secretkey,
                        ec2_key_pair_name=args.keypairname,
                        ec2_key_pair_file_path=args.keypairfile)
    cloud_provider.connect()

    # Storage stuff.
    storage = CloudStorage.VirtualStorageS3(aws_key=args.key,
                                            aws_secret_key=args.secretkey)
    storage.connect()

    if storage.bucket_exists(args.bucket):
        storage.erase_bucket(args.bucket)
        storage.delete_bucket(args.bucket)

    storage.create_bucket(args.bucket)

    # Setup all the instances in parallel
    virtual_instances = cloud_provider.create_instances(args.clients)
    test_object_list = []
    test_run_averages = []

    try:
        # Create all possible instances for this test,
        # and prepare as much as possible
        # before tests will begin.
        for vinstance in virtual_instances:
            test_object_list.append(Test(vinstance, args.bucket,
                               '/mnt/bucket', args.key, args.secretkey))

        # Run the tests, each step in parallel
        parallel_ops = classicTest.PerformParallelOperations(
            test_instances=test_object_list)
        parallel_ops.perform_all_operations()

        # Calc averages from the run data
        test_run_averages.append(RunAverages(
            parallel_ops.get_execute_test_results(), 1))

    except Exception:
        log.exception('Error while attempting to run test,'
                          ' attempting to clean up')

    # Cleanup the testbed
    cloud_provider.destroy_all_instances()
    storage.delete_bucket(args.bucket)

    # Output a report of the test runs.
    if len(test_run_averages) >= 1:
        report_results(test_run_averages, outfile=args.outfile)
    else:
        log.error("No results to report")

if __name__ == '__main__':
    main()
