import logging
import signal
import sys
import threading
import time
from configparser import SafeConfigParser

import paho.mqtt.publish as mqttpublish
import RPi.GPIO as GPIO

PUSHOVER_SOUNDS = None


def mqtt(msg, topic, retain=False):
    try:
        mqtt_auth = None
        if len(mqtt_username) > 0:
            mqtt_auth = {"username": mqtt_username, "password": mqtt_password}

        mqttpublish.single(
            topic,
            msg,
            qos=0,
            retain=retain,
            hostname=mqtt_hostname,
            port=mqtt_port,
            client_id=mqtt_clientid,
            keepalive=60,
            will=None,
            auth=mqtt_auth,
            tls=None,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        logging.debug("error sending {} mqtt to {} on topic {}: {}".format(msg, mqtt_hostname, topic, e))
        pass


def send_alert(message):
    if len(message) > 1:
        logging.info(message)
        if len(mqtt_topic) > 0:
            mqtt(message, mqtt_topic, False)


def send_appliance_active_message():
    send_alert(start_message)
    global appliance_active
    appliance_active = True


def send_appliance_inactive_message():
    send_alert(end_message)
    global appliance_active
    appliance_active = False


def vibrated(x):
    global vibrating
    global last_vibration_time
    global start_vibration_time
    logging.debug("Vibrated")
    last_vibration_time = time.time()
    if not vibrating:
        start_vibration_time = last_vibration_time
        vibrating = True


def heartbeat():
    current_time = time.time()
    logging.debug("HB at {}".format(current_time))
    global vibrating
    delta_vibration = last_vibration_time - start_vibration_time
    if vibrating and delta_vibration > begin_seconds and not appliance_active:
        send_appliance_active_message()
    if not vibrating and appliance_active and current_time - last_vibration_time > end_seconds:
        send_appliance_inactive_message()
    vibrating = current_time - last_vibration_time < 2
    threading.Timer(1, heartbeat).start()


logging.basicConfig(format="%(message)s", level=logging.INFO)

if len(sys.argv) == 1:
    logging.critical("No config file specified")
    sys.exit(1)

vibrating = False
appliance_active = False
last_vibration_time = time.time()
start_vibration_time = last_vibration_time

config = SafeConfigParser()
config.read(sys.argv[1])
verbose = config.getboolean("main", "VERBOSE")
sensor_pin = config.getint("main", "SENSOR_PIN")
begin_seconds = config.getint("main", "SECONDS_TO_START")
end_seconds = config.getint("main", "SECONDS_TO_END")

mqtt_hostname = config.get("mqtt", "mqtt_hostname")
mqtt_port = int(config.get("mqtt", "mqtt_port"))
mqtt_topic = config.get("mqtt", "mqtt_topic")
mqtt_availability_topic = config.get("mqtt", "mqtt_availability_topic")
mqtt_username = config.get("mqtt", "mqtt_username")
mqtt_password = config.get("mqtt", "mqtt_password")
mqtt_clientid = config.get("mqtt", "mqtt_clientid")

start_message = config.get("main", "START_MESSAGE")
end_message = config.get("main", "END_MESSAGE")
boot_message = config.get("main", "BOOT_MESSAGE")
term_message = config.get("main", "TERM_MESSAGE")

if verbose:
    logging.getLogger().setLevel(logging.DEBUG)


if len(mqtt_availability_topic) > 0:
    logging.debug("sending {} to {}".format(boot_message, mqtt_availability_topic))
    mqtt(boot_message, mqtt_availability_topic, True)


def sigterm_handler(signal, frame):
    logging.debug("received SIGTERM, cleaning up")
    if len(mqtt_availability_topic) > 0:
        logging.debug("sending {} to {}".format(term_message, mqtt_availability_topic))
        mqtt(term_message, mqtt_availability_topic, True)
    sys.exit()


signal.signal(signal.SIGTERM, sigterm_handler)


GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(sensor_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.add_event_detect(sensor_pin, GPIO.RISING)
GPIO.add_event_callback(sensor_pin, vibrated)

logging.info("Running config file {} monitoring GPIO pin {}".format(sys.argv[1], str(sensor_pin)))

threading.Timer(1, heartbeat).start()
