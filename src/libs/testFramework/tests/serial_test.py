"""
Please refer to top-level LICENSE file for copyright information
"""

import logging

from src.libs.testFramework import classicTest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('SerialTest')


class SerialTest(classicTest.TestInstance):
    def setup_environment(self):
        """
        The setup_environment method will pre-setup the test environment
        before the test executes.  Installs programs, packages, etc.
        :return:
        """
        log.info("Setup Environment")

    def pre_test_setup(self):
        """
        The pre_test_setup method will prepare the testing environment,
        mounting shares, etc.
        :return:
        """
        log.info("pre_test_setup")

    def execute_test(self):
        """
        The execute_test method will trigger the actual test and record
        results.
        :param file_type: file_type to use for the operation(zero/random)
        :return:
        """
        log.info("execute_test")

    def cleanup(self):
        """
        The cleanup method will perform needed cleanup.
        :return:
        """
        log.info("cleanup")

test = SerialTest(virtual_instance=None)
test.perform_all_operations()
