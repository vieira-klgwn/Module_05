import paho.mqtt.client as mqtt

MQTT_HOST = "157.173.101.159"
MQTT_PORT = 1883
TOPIC = "vision/Winners/movement"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    print("Topic:", msg.topic)
    print("Message:", msg.payload.decode())
    print("-" * 40)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_HOST, MQTT_PORT, 60)
client.loop_forever()