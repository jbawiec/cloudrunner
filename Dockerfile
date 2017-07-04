FROM ubuntu
ADD src /mydir/src/
add keys /mydir/keys/

# Install programs
RUN apt-get update && apt-get install -y \
build-essential \
libssl-dev \
libffi-dev \
python \
python-dev \
python-pip

# Update PIP
RUN pip install --upgrade pip

# Install Python libraries
RUN pip install \
boto \
paramiko \
pycrypto \
fabric
