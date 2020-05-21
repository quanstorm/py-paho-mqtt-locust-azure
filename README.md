# py-paho-mqtt-locust-azure
# Overview

A simulation load test using Locust IO to send device messages to Azure IoT hub using MQTT 
Based on https://github.com/concurrencylabs/mqtt-locust, which is based on https://github.com/ajm188/mqtt-locust 

**The MQTT Locust client**
- Think of the MQTTLocust class inherits the Locust class
- Each IoT device is represented by the Asset class, which inherits MQTTLocust class. 
- The IoT device (Asset) is uniquely identified by a device ID which in this case is the Tag
- AssetBehavior class is a TaskSet class

Locust Load test application will be configured to run in distributed mode. For that, we have one Master node and 100 slave nodes.

Each slave VM can spawn 300 assets, so for 30k assets we need 100 cores i.e. 100 slaves
For simplicity, a slave VM is a small Azure B1ms type with 1 CPU and 2 GB RAM
Each VM configured as follows:
- SSH for connection
- static IP
- Port 8089 (only for master node), 5557, 5558 (for Locust communication)
- Software: see server-config-tasks.sh for details

# The Locust Master Node
## Create Master node
Use the script under  utilities/vm-create/template to create a VM on Azure

## Copy files
Suppose the VM can be connected through sa@137.116.82.127

Run this sequence of commands from your local box to transfer files up to the Master VM

From the directory /utilities/vm-create:

scp scaletest_rsa.key ssh sa@137.116.82.127:/home/sa

scp ssh-keyscan.sh sa@137.116.82.127:/home/sa

scp server-config-tasks.sh sa@137.116.82.127:/home/sa

scp scp-server-config.sh sa@137.116.82.127:/home/sa

scp run-remote-vm-config.sh sa@137.116.82.127:/home/sa

scp scp-locust-scripts.sh sa@137.116.82.127:/home/sa

scp scp-launch-scripts.sh sa@137.116.82.127:/home/sa

scp -r launch-scripts sa@137.116.82.127:/home/sa

scp start-locust-cluster.sh sa@137.116.82.127:/home/sa

## Make the SSH key persistent on reboot
cd ~/.ssh

vim config

(add the line below and save)

IdentityFile ~/scaletest_rsa.key

## Configure software packages
./server-config-tasks.sh

# The Locust Slave VMs
Perform the following tasks to create and configure the Locust slave VMs

## Create Locust slave VMs
From your local box: To add additional Locust nodes to the cluster, create them as Azure VMs using the following procedure

Edit the parameters.json: The definition of each VM is contained in the parameters.json. For each new VM, just need to update the VM name and its network name

Run the CLI command to create the VM, replacing the -n parameter with the VM name

Run the deploy.sh under /vm-create/template

Collect the connection info for each VM (using Azure UI)

## Update script files

From your local box: Edit these files to include the new VMs:

list-of-vm.txt: include ONLY the newly created VMs, each on its own line in the format of sa@{IP}

scp-launch-scripts.sh: each VM should be assign a UNIQUE launch script. The launch script files are pre-created under the ../launch-scripts folder

start-locust-cluster.sh: add the new VMs to the list that Locust should spin up

Then copy the modified script files to the Master node:

cd /Users/quan/source/parker-scale-test/utilities/vm-create

./scp-updated-scripts.sh


## Run the scripts to update
./ssh-keyscan.sh list-of-vm.txt

./scp-server-config.sh list-of-vm.txt

./scp-locust-scripts.sh list-of-vm.txt

./scp-launch-scripts.sh

./run-remote-vm-config.sh list-of-vm.txt


# Launch Data Load Test 
Use screen from the Master node to launch the test. 

* Create a named session, say "master"
screen -S master
* Start the Locust cluster
./start-locust-cluster.sh

* You can now launch the Locust UI from your favorite browser and enter the test parameters to start the swarm

* You can check the log to see how Locust test was launched

tail -f nohup.out


# Stop test and collect data
Locust has a Stop Test button. In distributed mode this is not reliable in stopping the slave VMs, so do the following when you are done with a test run:

* Click the Stop Tests on Locust UI
* Download the Locust CSV data files
* Screenshot the Azure custom built dashboard that monitors the Scale Test
* Stop (Deallocate) all the Locust VMs. This also saves on Azure operating cost

# Notes
**Reason for increasing the maxfiles limit:**
If you may notice, at the top of the test locust script is the line:
```
resource.setrlimit(resource.RLIMIT_NOFILE, (999999, 999999))
```

This is required because, after a few hundred users, the test will start to run into OS limits without this line.  Because of the changes this makes you will have to run the script using `sudo`.
