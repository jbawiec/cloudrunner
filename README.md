# cloudrunner
Library to help run basic python tests in the cloud

Designed to allow users to run multiple concurrent tests in AWS environment.

TODOs:
* Need to add Azure support
* Need to better abstract test code, and provide good examples.

BUGS:
* After test run, console acccess is a bit off, something is messing with the shell.

Needed system programs/libraries:
build-essential \
libssl-dev \
libffi-dev \
python \
python-dev \
python-pip

Needed python libraries:
boto \
paramiko \
pycrypto \
fabric



How To Run:
1. Create keypair: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html


Commandline:
2. cd to the cloudrunner directory
3. export PYTHONPATH=.
4. python src/tests/AwsRunner/AwsRunner.py --key [AWS key] --secretkey [AWS secret key] --keypairname [keypair name] --keypairfile [path to pem file] --region [region] --bucket [bucket_name] --clients [number of parallel clients] --outfile ./results.json


Dockerfile:
0. Copy your .pem file into the keys directory.
1. Build the image:  docker build -t awsrunner .
2. Login: docker run -it aws /bin/bash
3. cd /cloudrunner
4. export PYTHONPATH=.
4. python src/tests/AwsRunner/AwsRunner.py --key [AWS key] --secretkey [AWS secret key] --keypairname [keypair name] --keypairfile [path to pem file] --region [region] --bucket [bucket_name] --clients [number of parallel clients] --outfile ./results.json

