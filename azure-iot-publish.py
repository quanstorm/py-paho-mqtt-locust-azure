import json
import random
import resource
import ssl
import time
import logging
import sys
import os

from datetime import datetime
from locust import TaskSet, task
from mqtt_locust import MQTTLocust
from logging.handlers import RotatingFileHandler

resource.setrlimit(resource.RLIMIT_NOFILE, (999999, 999999))


def append_file_logger():
    root_logger = logging.getLogger()
    # '%(name)s - %(levelname)s - %(message)s'
    log_format = "%(asctime)s.%(msecs)03d000 [%(levelname)s] {0}/%(name)s : %(message)s"
    formatter = logging.Formatter(log_format, '%Y-%m-%d %H:%M:%S')
    file_handler = RotatingFileHandler('./locust.log', maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)


append_file_logger()

# this value is the number of seconds to be used before retrying operations (valid for QoS >1)
RETRY = 5

# ms
PUBLISH_TIMEOUT = 10000
SUBSCRIBE_TIMEOUT = 10000

with open("scenario_json/dataset.json", 'r') as f:
    data = json.load(f)[0]

my_locust = os.getenv("MYLOCUST", '')
if my_locust == '':
    raise ValueError(
        "Please set environment variable MYLOCUST to tell the script which set of assets to use")

list_of_org_ids = my_locust.split(":")

logging.info("STARTING LOCUST TEST with the following Orgs: " + " ".join(list_of_org_ids))


"""
In Locust Asset class:
Build myAssetList that contains the assets, their org_id, template_id, and payload
"""
myAssetList = []
for org_id in list_of_org_ids:
    matchingOrg = filter(lambda x: x["orgId"] == org_id, data["organizations"])
    for asset in matchingOrg[0]["assets"]:
        asset_info = {"nameTag": asset["nametag"],
                      "gatewayId": asset["gatewayId"],
                      "payloadTemplate": matchingOrg[0]['payload']}
        myAssetList.append(asset_info)


def payload(self, gateway_id, payload_template):
    current_milli_time = int(round(time.time() * 1000))
    dec_lat = random.random()
    dec_long = random.random()
    currentlatitude = 39.73 + dec_lat
    currentlongitude = -105.5221 + dec_long

    time_stamped_packet = payload_template % (
        current_milli_time, gateway_id, currentlatitude, currentlongitude)
    # self.logger.info(time_stamped_packet)
    return time_stamped_packet


class AssetBehavior(TaskSet):

    tag = "TAG_NOT_VALID"
    topic = "TOPIC_NOT_DEFINED"

    def on_start(self):
        # allow for the connection to be established before publishing on the MQTT topic
        time.sleep(5)
        # Thanks to Mike Dearman for the next line
        # https://github.com/locustio/locust/issues/906
        self.tag = self.locust.nameTag
        self.gateway_id = self.locust.gatewayId
        self.datapoint_template = self.locust.payload_template
        self.logger = self.locust.logger
        self.topic = "devices/{}/messages/events/".format(self.tag)
        self.logger.info("2. Start sending data packets for device ID {tag}".format(tag=self.tag))

    @task
    def sendPacket2Cloud(self):
        self.client.publish(self.topic, payload=payload(
            self, self.gateway_id, self.datapoint_template), qos=0, timeout=PUBLISH_TIMEOUT)


class Asset(MQTTLocust):
    """
    This is the swarming locust!
    Locust hatches as many instances of this class as defined in the GUI.
    Each instance of Asset represents a device that will connect to Azure IoT.
    When a load test is started, each instance of this class will start executing their TaskSet.
    What happens then is that each TaskSet will pick one of its tasks and call it.
    It will then wait a number of milliseconds, chosen at random between the Locust class min_wait and max_wait attributes
    (unless min_wait/max_wait have been defined directly under the TaskSet, in which case it will use its own values instead).
    Then it will again pick a new task to be called, wait again, and so on.
    """

    # QT: class variables, shared by all locust instances
    #   The DigiCert Baltimore Root Certificate is used by Azure to secure the TLS connection
    #   The IoT cert and private key are from the self-signed cert used by all Test Assets
    path_to_ca_cert = "selfsigned/Digicert-Baltimore.cer"
    path_to_iot_cert = "selfsigned/cert.pem"
    path_to_iot_private_key = "selfsigned/key.pem"
    nameTag = "NT_NOT_DEFINED"

    def __init__(self):
        # QT: each asset is identified by its ID which in this case is the nameTag
        if len(myAssetList) > 0:
            self.asset_data = myAssetList.pop()
            self.nameTag = self.asset_data['nametag']
            self.payload_template = self.asset_data['payloadTemplate']
            self.gatewayId = self.asset_data["gatewayId"]

            self.logger = logging.getLogger('asset-%s' % self.nameTag)
            self.logger.info("1. =====Asset spawned: {tag}".format(tag=self.nameTag))
            # QT: initialize the device ID in the MQTTLocust class
            super(Asset, self).__init__(device_id=self.nameTag)

    task_set = AssetBehavior

    # milliseconds
    min_wait = 29000
    max_wait = 31000
