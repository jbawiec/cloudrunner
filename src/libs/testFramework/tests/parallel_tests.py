import logging
import time
from src.libs.testFramework import classicTest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('SerialTest')

"""
Please refer to top-level LICENSE file for copyright information
"""

class ParallelTest(classicTest.TestInstance):

    def __init__(self, sleep=0):
        super(self.__class__, self).__init__(virtual_instance=None)
        self.sleep=sleep

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
        log.info("Sleeping for %s", self.sleep)
        time.sleep(self.sleep)
        log.info("Done sleeping")


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

test1 = ParallelTest(sleep=10)
test2 = ParallelTest()

operate = classicTest.PerformParallelOperations(test_instances=[test1, test2])
operate.perform_all_operations()
