"""
Please refer to top-level LICENSE file for copyright information
"""

import logging
import threading
from src.libs.utils import ThreadWithError

log = logging.getLogger(__name__)


class TestInstance(object):
    """
    TestInstance class encapsulates the test logic.  If other tests are needed
    they can extend this class and override methods as necessary.
    """
    def __init__(self, virtual_instance):
        self._vinstance = virtual_instance

    def get_virtual_instance(self):
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

    def pre_test_setup(self):
        """
        The pre_test_setup method will prepare the testing environment,
        mounting shares, etc.
        :return:
        """

    def execute_test(self):
        """
        The execute_test method will trigger the actual test and record
        results.
        :param file_type: file_type to use for the operation(zero/random)
        :return:
        """

    def cleanup(self):
        """
        The cleanup method will perform needed cleanup.
        :return:
        """

    def perform_all_operations(self):
        try:
            self.setup_environment()
        except Exception as err:
            log.exception("Failed to setup environment")
            raise

        try:
            self.pre_test_setup()
        except Exception as err:
            log.exception("Failed to perform pre-setup")
            raise

        try:
            self.execute_test()
        except Exception as err:
            log.exception("Failed to perform execution")
            raise

        try:
            self.cleanup()
        except Exception as err:
            log.exception("Failed to cleanup")
            raise


class PerformParallelOperations(object):
    def __init__(self, test_instances=None):
        self.tests = test_instances
        self.results = []
        if not self.tests or len(self.tests) == 0:
            raise Exception("No tests specified")

    def _thread_run_and_gather(self, test, method, lock):
        result = getattr(test, method)()
        with lock:
            self.results.append({method: result})

    def _perform_ops(self, method=None, timeout_sec=900, lock=None, args=None):
        thread_list = []
        for test in self.tests:
            t = ThreadWithError(target=self._thread_run_and_gather,
                                args=[test,
                                      method,
                                      lock])
            thread_list.append(t)
            t.start()

        for t in thread_list:
            t.join(timeout_sec)
            if t.is_alive():
                raise RuntimeError('Timed out during threaded operation')
            if t.has_error():
                raise RuntimeError('Error during threaded operation')

    def perform_all_operations(self):

        for method in ['setup_environment',
                       'pre_test_setup',
                       'execute_test',
                       'cleanup']:
            try:
                lockobj = threading.Lock()
                self._perform_ops(method=method, lock=lockobj)
            except Exception as err:
                log.exception('Exception while performing:%s', method)
                raise
        return self.results

    def _get_results(self, method=None):
        method_result = []
        for result in self.results:
            if method in result:
                method_result.append(result[method])
        return method_result

    def get_execute_test_results(self):
        return self._get_results(method='execute_test')
