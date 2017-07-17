import threading
import logging

log = logging.getLogger(__name__)


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
            log.exception("Hit error in thread:%s", err.message)
            self.error = True

    def has_error(self):
        return self.error
