"""
Please refer to top-level LICENSE file for copyright information
"""

from boto.s3.connection import S3Connection


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
