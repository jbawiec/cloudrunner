# cloudrunner
Library to help run basic python tests in the cloud

Designed to allow users to run multiple concurrent tests in AWS environment.

At this point it's very rough, mostly got-it-working with some handy abstractions.

TODOs:
* Need to break out AWS/virtual code into its own library.
* Need to break out Threading class to its own library.
* Need to add Azure support
* Need to better abstract test code, and provide good examples.
* Need a cleaner docker image creation, dummy .pem files, etc.

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
2. python src/AwsRunner.py --key [AWS key] --secretkey [AWS secret key] --keypairname [keypair name] --keypairfile [path to pem file] --region [region] --bucket [bucket_name] --clients 2 --outfile ./results.json


Dockerfile:
0. Copy your .pem file into the same directory as Dockerfile, and add a line to have this added to the image.
1. Build the image:  docker build -t awsrunner .
2. Login: docker run -it aws /bin/bash
3. cd /mydir
4. python src/AwsRunner.py --key [AWS key] --secretkey [AWS secret key] --keypairname [keypair name] --keypairfile [path to pem file] --region [region] --bucket [bucket_name] --clients 2 --outfile ./results.json

