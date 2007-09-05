#!/usr/bin/env python
# Copyright (c) 2006,2007 Mitch Garnaat http://garnaat.org/
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
import getopt, sys, imp, time
import boto
from boto.utils import get_instance_userdata

usage_string = """
SYNOPSIS
    launch_ami.py -m module -c class_name -a ami_id -b bucket_name [-r] [-s]
                  [-g group] [-k key_name] [-n num_instances]
                  [-w working_dir] extra_data
    Where:
        module - the name of the Python module you wish to pass to the AMI
        class_name - the name of the class to be instantiated within the module
        ami_id - the id of the AMI you wish to launch
        bucket_name - the name of the bucket in which the script will be stored
        group - the name of the security group the instance will run in
        key_name - the name of the keypair to use when launching the AMI
        num_instances - how many instances of the AMI to launch (default 1)
        working_dir - path on newly launched instance used for storing script
        extra_data - additional name-value pairs that will be passed as
                     userdata to the newly launched instance.  These should
                     be of the form "name=value"
        The -r option reloads the Python module to S3 without launching
        another instance.  This can be useful during debugging to allow
        you to test a new version of your script without shutting down
        your instance and starting up another one.
        The -s option tells the script to run synchronously, meaning to
        wait until the instance is actually up and running.  It then prints
        the IP address and internal and external DNS names before exiting.
"""

def usage():
    print usage_string
    sys.exit()

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'a:b:c:g:hk:m:rsw:',
                                   ['ami', 'bucket', 'class', 'group', 'help',
                                    'keypair', 'module', 'numinstances',
                                    'reload', 'working_dir'])
    except:
        usage()
    params = {'module_name' : None,
              'class_name' : None,
              'bucket_name' : None,
              'group' : 'default',
              'keypair' : None,
              'ami' : None,
              'working_dir' : None}
    reload = None
    wait = None
    ami = None
    for o, a in opts:
        if o in ('-a', '--ami'):
            params['ami'] = a
        if o in ('-b', '--bucket'):
            params['bucket_name'] = a
        if o in ('-c', '--class'):
            params['class_name'] = a
        if o in ('-g', '--group'):
            params['group'] = a
        if o in ('-h', '--help'):
            usage()
        if o in ('-k', '--keypair'):
            params['keypair'] = a
        if o in ('-m', '--module'):
            params['module_name'] = a
        if o in ('-n', '--num_instances'):
            params['num_instances'] = int(a)
        if o in ('-r', '--reload'):
            reload = True
        if o in ('-s', '--synchronous'):
            wait = True
        if o in ('-w', '--working_dir'):
            params['working_dir'] = a

    # check required fields
    required = ['ami', 'bucket_name', 'class_name', 'module_name']
    for pname in required:
        if not params.get(pname, None):
            print '%s is required' % pname
            usage()
    # first copy the desired module file to S3 bucket
    if reload:
        print 'Reloading module %s to S3' % params['module_name']
    else:
        print 'Copying module %s to S3' % params['module_name']
    l = imp.find_module(params['module_name'])
    c = boto.connect_s3()
    bucket = c.get_bucket(params['bucket_name'])
    key = bucket.new_key(params['module_name']+'.py')
    key.set_contents_from_file(l[0])
    params['script_md5'] = key.md5
    # we have everything we need, now build userdata string
    l = []
    for k, v in params.items():
        if v:
            l.append('%s=%s' % (k, v))
    c = boto.connect_ec2()
    l.append('aws_access_key_id=%s' % c.aws_access_key_id)
    l.append('aws_secret_access_key=%s' % c.aws_secret_access_key)
    for kv in args:
        l.append(kv)
    s = '|'.join(l)
    if not reload:
        rs = c.get_all_images([params['ami']])
        img = rs[0]
        r = img.run(user_data=s, key_name=params['keypair'],
                    security_groups=[params['group']],
                    max_count=params.get('num_instances', 1))
        print 'AMI: %s - %s (Started)' % (params['ami'], img.location)
        print 'Reservation %s contains the following instances:' % r.id
        for i in r.instances:
            print '\t%s' % i.id
        if wait:
            running = False
            while not running:
                time.sleep(30)
                [i.update() for i in r.instances]
                status = [i.state for i in r.instances]
                print status
                if status.count('running') == len(r.instances):
                    running = True
            for i in r.instances:
                print 'Instance: %s' % i.ami_launch_index
                print 'Public DNS Name: %s' % i.public_dns_name
                print 'Private DNS Name: %s' % i.private_dns_name

if __name__ == "__main__":
    main()

