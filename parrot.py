#!/usr/bin/env python3

# based on https://github.com/Bamorph/Meshtastic_MQTT_Terminal/

import paho.mqtt.client as mqtt
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import random
import time
#from plyer import notification


def create_node_id(node_number):
    return f'!{hex(node_number)[2:]:0>8}'

def decode_node_id(node_id):
    hex_string = node_id[1:]  # Removing the '!' character
    return int(hex_string, 16)


# Default settings
MQTT_BROKER = "mqtt.meshtastic.org"
MQTT_PORT = 1883
MQTT_USERNAME = "meshdev"
MQTT_PASSWORD = "large4cats"
#root_topic = "msh/ANZ/2/c/"
#channel = "LongFast"
#key = "1PG7OiApB1nwvP+rz05pAQ=="
#root_topic = "msh/US/SecKC/2/e/"
root_topic = "msh/US/SecKC/2/"
#channel = "SecKC-Test"
channel = "map"
key = "redacted"

padded_key = key.ljust(len(key) + ((4 - (len(key) % 4)) % 4), '=')
replaced_key = padded_key.replace('-', '+').replace('_', '/')
key = replaced_key

broadcast_id = 4294967295

# Convert hex to int and remove '!'
#node_number = 2882396642 # int('abcd', 16)
bot_nodenum = int('abcd1234', 16)
#node_number = int('e2e38f58', 16) #Azzr
#node_number = int('7c5afde0', 16) #TD0 taco
bot_nodeid = create_node_id(bot_nodenum)

print(f'AUTO-ROUTER NODE-ID: {bot_nodeid}')


def set_topic(source_nodenum):
    global subscribe_topic, publish_topic
    topic_name = create_node_id(source_nodenum)
    subscribe_topic = root_topic + channel + "/#"
    publish_topic = root_topic + channel + "/" + topic_name



def current_time():
    current_time_seconds = time.time()
    current_time_struct = time.localtime(current_time_seconds)
    current_time_str = time.strftime("%H:%M:%S", current_time_struct)
    return(current_time_str)

def xor_hash(data):
    result = 0
    for char in data:
        result ^= char
    return result

def generate_hash(name, key):
    replaced_key = key.replace('-', '+').replace('_', '/')
    key_bytes = base64.b64decode(replaced_key.encode('utf-8'))
    h_name = xor_hash(bytes(name, 'utf-8'))
    h_key = xor_hash(key_bytes)
    result = h_name ^ h_key
    return result


def publish_message(source_id, destination_id, message):
    global key
    # print(int(destination_id[1:], 16))
    message_text = message
    if message_text:
        encoded_message = mesh_pb2.Data()
        encoded_message.portnum = portnums_pb2.TEXT_MESSAGE_APP 
        encoded_message.payload = message_text.encode("utf-8")

    generate_mesh_packet(source_id, destination_id, encoded_message)


def generate_mesh_packet(source_id, destination_id, encoded_message):
    mesh_packet = mesh_pb2.MeshPacket()

    setattr(mesh_packet, "from", source_id)
    # setattr(mesh_packet, "long_name", "AUTO-REPLY")

    mesh_packet.id = random.getrandbits(32)
    mesh_packet.to = destination_id
    mesh_packet.want_ack = False
    mesh_packet.channel = generate_hash(channel, key)
    mesh_packet.hop_limit = 3

    if key == "":
        mesh_packet.decoded.CopyFrom(encoded_message)
    else:
        mesh_packet.encrypted = encrypt_message(channel, key, mesh_packet, encoded_message, source_id)

    service_envelope = mqtt_pb2.ServiceEnvelope()
    service_envelope.packet.CopyFrom(mesh_packet)
    service_envelope.channel_id = channel
    service_envelope.gateway_id = create_node_id(source_id)

    payload = service_envelope.SerializeToString()
    set_topic(source_id)
    client.publish(publish_topic, payload)


def encrypt_message(channel, key, mesh_packet, encoded_message, source_id):
    mesh_packet.channel = generate_hash(channel, key)
    key_bytes = base64.b64decode(key.encode('ascii'))
    nonce_packet_id = mesh_packet.id.to_bytes(8, "little")
    nonce_from_node = source_id.to_bytes(8, "little")
    nonce = nonce_packet_id + nonce_from_node

    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_bytes = encryptor.update(encoded_message.SerializeToString()) + encryptor.finalize()

    return encrypted_bytes


known_id_list = []

def process_message(mp, text_payload, is_encrypted):
    mp_id = getattr(mp, "id")
    mp_to = getattr(mp, "to")
    mp_from = getattr(mp, "from")
    if mp_id not in known_id_list:
        known_id_list.append(mp_id)
        print(known_id_list)
        print(mp)
        text = {
            "message": text_payload,
            "from": getattr(mp, "from"),
            "id": getattr(mp, "id"),
            "to": getattr(mp, "to")
        }

        source_id = mp_from
        source_nodeid = create_node_id(getattr(mp, "from"))
        
        if create_node_id(getattr(mp, "from")) != bot_nodeid:
            print(f'message from {getattr(mp, "from")} / {source_nodeid}')
            time.sleep(1)
            publish_message(source_id, broadcast_id, f'Taco bot says: {text_payload}')
        else:
            print(f'message from this script')
    else:
        print(f'packet {mp_id} already seen: {text_payload}')


def decode_encrypted(message_packet):
    try:
        key_bytes = base64.b64decode(key.encode('ascii'))
      
        nonce_packet_id = getattr(message_packet, "id").to_bytes(8, "little")
        nonce_from_node = getattr(message_packet, "from").to_bytes(8, "little")
        nonce = nonce_packet_id + nonce_from_node

        cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_bytes = decryptor.update(getattr(message_packet, "encrypted")) + decryptor.finalize()

        data = mesh_pb2.Data()
        data.ParseFromString(decrypted_bytes)
        message_packet.decoded.CopyFrom(data)
        # print(message_packet)
        
        if message_packet.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
            text_payload = message_packet.decoded.payload.decode("utf-8")
            is_encrypted = True
            process_message(message_packet, text_payload, is_encrypted)
            # print(f"{text_payload}")


        elif message_packet.decoded.portnum == portnums_pb2.NODEINFO_APP:
                info = mesh_pb2.User()
                info.ParseFromString(message_packet.decoded.payload)
                # print(info)

                # notification.notify(
                # title = "Meshtastic",
                # message = f"{info}",
                # timeout = 10
                # )
        elif message_packet.decoded.portnum == portnums_pb2.MAP_REPORT_APP:
            print('map packet')
        else:
            print('unknown')



    except Exception as e:
        pass
        # print(f"Decryption failed: {str(e)}")

def on_connect(client, userdata, flags, rc, properties = None):
    if rc == 0:
        print(f"Connected to {MQTT_BROKER} on topic {channel}")
    else:
        print(f"Failed to connect to MQTT broker with result code {str(rc)}")

def on_message(client, userdata, msg):
    service_envelope = mqtt_pb2.ServiceEnvelope()
    
    # auto_reply(service_envelope)
    try:
        service_envelope.ParseFromString(msg.payload)

        # print(service_envelope)
        
        message_packet = service_envelope.packet
        # print(message_packet)
        


    except Exception as e:
        print(f"Error parsing message: {str(e)}")
        return
    
    if message_packet.HasField("encrypted") and not message_packet.HasField("decoded"):
        decode_encrypted(message_packet)
    else:
        decode_encrypted(message_packet)

if __name__ == '__main__':
    # client = mqtt.Client(client_id="", clean_session=True, userdata=None)
    client = mqtt.Client() #mqtt.CallbackAPIVersion.VERSION2)

    client.on_connect = on_connect
    client.username_pw_set(username=MQTT_USERNAME, password=MQTT_PASSWORD)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    client.on_message = on_message

    subscribe_topic = f"{root_topic}{channel}/#"
    # subscribe_topic = f"{root_topic}{channel}/{node_id}"

    client.subscribe(subscribe_topic, 0)

    while client.loop() == 0:
        pass
