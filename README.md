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

See more details in this article https://medium.com/@quantstorm/simulate-an-iot-swarm-with-locust-io-and-azure-52cba966b51b
