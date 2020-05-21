from locust import Locust, TaskSet, task, events
from datetime import datetime
from datetime import timedelta
import math
import time
import json
import random
import resource
import requests
import sys
import ssl
import logging

import paho.mqtt.client as mqtt


REQUEST_TYPE = 'MQTT'
MESSAGE_TYPE_PUB = 'PUB'
MESSAGE_TYPE_SUB = 'SUB'


def time_delta(t1, t2):
    return int((t2 - t1) * 1000)


def fire_locust_failure(**kwargs):
    events.request_failure.fire(**kwargs)


def fire_locust_success(**kwargs):
    events.request_success.fire(**kwargs)


class LocustError(Exception):
    pass


class TimeoutError(ValueError):
    pass


class ConnectError(Exception):
    pass


class DisconnectError(Exception):
    pass


class Message(object):

    def __init__(self, type, qos, topic, payload, start_time, timeout, name):
        self.type = type,
        self.qos = qos,
        self.topic = topic
        self.payload = payload
        self.start_time = start_time
        self.timeout = timeout
        self.name = name

    def timed_out(self, total_time):
        return self.timeout is not None and total_time > self.timeout


class MQTTClient(mqtt.Client):

    def __init__(self, *args, **kwargs):
        super(MQTTClient, self).__init__(*args, **kwargs)
        self.on_publish = self.locust_on_publish
        self.on_subscribe = self.locust_on_subscribe
        self.on_disconnect = self.locust_on_disconnect
        self.on_connect = self.locust_on_connect
        self.pubmmap = {}
        self.submmap = {}
        self.defaultQoS = 0
        self.device_id = kwargs.get('client_id')
        self.logger = logging.getLogger('asset-%s' % self.device_id)

    def tls_set(self, ca_certs, certfile=None, keyfile=None, cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None):
        start_time = time.time()

        try:
            super(MQTTClient, self).tls_set(ca_certs,
                                            certfile,
                                            keyfile,
                                            cert_reqs,
                                            tls_version,
                                            ciphers)
        except Exception as e:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name='tls_set',
                response_time=time_delta(start_time, time.time()),
                exception=e)

    # retry is not used at the time since this implementation only supports QoS 0
    def publish(self, topic, payload=None, qos=0, retry=5, name='publish', **kwargs):
        timeout = kwargs.pop('timeout', 10000)
        start_time = time.time()

        # QT: for a list of errors, see
        # https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py

        try:
            err, mid = super(MQTTClient, self).publish(
                topic,
                payload=payload,
                qos=qos,
                **kwargs
            )
            if err:
                fire_locust_failure(
                    request_type=REQUEST_TYPE,
                    name=name,
                    response_time=time_delta(start_time, time.time()),
                    exception=ValueError(err)
                )

                print ("publish: err,mid:["+str(err)+","+str(mid)+"]")
            self.pubmmap[mid] = Message(
                MESSAGE_TYPE_PUB, qos, topic, payload, start_time, timeout, name
            )
            # print ("publish: Saved message - mqtt client obj id:["+str(id(self))+"] - pubmmap obj id:["+str(id(self.pubmmap))+"] in dict - mid:["+str(mid)+"] - message object id:["+str(id(self.pubmmap[mid]))+"]")
        except Exception as e:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=name,
                response_time=time_delta(start_time, time.time()),
                exception=e,
            )
            print (str(e))

    # retry is not used at the time since this implementation only supports QoS 0
    def subscribe(self, topic, qos=0, retry=5, name='subscribe', timeout=15000):
        # print ("subscribing to topic:["+topic+"]")
        start_time = time.time()
        try:
            err, mid = super(MQTTClient, self).subscribe(
                topic,
                qos=qos
            )
            self.submmap[mid] = Message(
                MESSAGE_TYPE_SUB, qos, topic, "", start_time, timeout, name
            )
            if err:
                raise ValueError(err)
                print ("Subscribed to topic with err:["+str(err)+"]messageId:["+str(mid)+"]")
        except Exception as e:
            total_time = time_delta(start_time, time.time())
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=name,
                response_time=total_time,
                exception=e,
            )
            print ("Exception when subscribing to topic:["+str(e)+"]")

    def locust_on_connect(self, client, flags_dict, userdata, rc):
        # self.logger.info("Connection returned result: "+mqtt.connack_string(rc))
        self.logger.info("Device connected with result code: " + str(rc))
        fire_locust_success(
            request_type=REQUEST_TYPE,
            name='connect',
            response_time=0,
            response_length=0
        )

    def locust_on_publish(self, client, userdata, mid):
        """
        Paho documentation regarding on_publish event:
        'For messages with QoS levels 1 and 2, this means that the appropriate handshakes have
        completed. For QoS 0, this simply means that the message has left the client.'
        This means that the value we record in fire_locust_success for QoS 0 will always
        be very low and not a meaningful metric. The interesting part comes when we analyze
        metrics emitted by the system on the other side of the MQTT broker (the systems processing
        incoming data from things).
        """

        end_time = time.time()

        if self.defaultQoS == 0:
            # if QoS=0, we reach the callback before the publish() has enough time to update the pubmmap dictionary
            time.sleep(float(0.5))

        message = self.pubmmap.pop(mid, None)
        # self.logger.info("on_publish  - mqtt client obj id:["+str(id(self))+"] - pubmmap obj id:["+str(
        #     id(self.pubmmap))+"] - mid:["+str(mid)+"] - message obj id:["+str(id(message))+"]")
        if message is None:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name="message_found",
                response_time=0,
                exception=ValueError("Published message could not be found"),
            )
            return

        total_time = time_delta(message.start_time, end_time)
        if message.timed_out(total_time):
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=message.name,
                response_time=total_time,
                exception=TimeoutError("publish timed out"),
            )
            print("report publish failure - response_time:["+str(total_time)+"]")
        else:
            fire_locust_success(
                request_type=REQUEST_TYPE,
                name=message.name,
                response_time=total_time,
                response_length=len(message.payload),
            )
            # print("Device sent message - response_time:["+str(total_time)+"]")

    def locust_on_subscribe(self, client, userdata, mid, granted_qos):
        end_time = time.time()
        message = self.submmap.pop(mid, None)
        if message is None:
            print ("did not find message for on_subscribe")
            return
        total_time = time_delta(message.start_time, end_time)
        if message.timed_out(total_time):
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=message.name,
                response_time=total_time,
                exception=TimeoutError("subscribe timed out"),
            )
            self.logger.info("report subscribe failure - response_time:["+str(total_time)+"]")
        else:
            fire_locust_success(
                request_type=REQUEST_TYPE,
                name=message.name,
                response_time=total_time,
                response_length=0,
            )
            print("report subscribe success - response_time:["+str(total_time)+"]")

    def locust_on_disconnect(self, client, userdata, rc):
        self.logger.info("Device disconnected with result code: " + str(rc))
        fire_locust_failure(
            request_type=REQUEST_TYPE,
            name='disconnect',
            response_time=0,
            exception=DisconnectError("disconnected"),
        )
        self.reconnect()


class MQTTLocust(Locust):
    """
    This is the main class, inherited by the Asset class
    """

    def __init__(self, device_id=None, *args, **kwargs):
        # QT: super of the child class Locust
        super(Locust, self).__init__(*args, **kwargs)
        if self.host is None:
            raise LocustError("You must specify a host")
        # We want to control the client_id that is set in Paho.
        # Each client_id should match a device id in the Azure IoT Registry
        self.device_id = device_id
        self.client = MQTTClient(client_id=self.device_id, protocol=mqtt.MQTTv311)
        try:
            [host, port] = self.host.split(":")
        except:
            host, port = self.host, 8883
        # this logger is from the Asset parent class
        self.logger.info("Establishing MQTT client connection for device ID " + self.device_id)

        try:
            # QT: must have this to work. Original sample, for AWS, doesn't have this line
            self.client.username_pw_set(username=self.host + "/" + self.device_id, password="")

            # We want to do TLS client authentication,
            # that is, the script needs to authenticate to the IoT hub
            self.client.tls_set(ca_certs=self.path_to_ca_cert, certfile=self.path_to_iot_cert, keyfile=self.path_to_iot_private_key,
                                tls_version=ssl.PROTOCOL_TLSv1)

            # It is important to do an asynchronous connect, given that we will have
            # multiple connections happening in a single server during a Locust test
            # QT: Used in conjunction with loop_start()
            self.client.connect_async(host, port)
            self.client.loop_start()
        except Exception as e:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name='connect',
                response_time=time_delta(start_time, time.time()),
                exception=ConnectError("Could not connect to host:["+host+"]")
            )
