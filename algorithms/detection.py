import paho.mqtt.client as mqtt
import time
import json
import numpy

from trigger import sta_lta
from trigger import trigger_time
from trigger import accel_value


# initializing empty variables
inbox = []

# trigger parameters
long_window = 11
short_window = 1
trigger_level = 3


def set_time(times, sr, N):
    """
    times = time stamps by fifo in each payload 
    sr = sample rate 
    N = number of data samples
    """
    
    # number of fifos
    nfifo = len(times)
    
    # create an empty variable to allocate the 
    diff = []
    
    # Loop over the times of each fifo
    for i, item in enumerate(times[0:-1]):
        diff.append(times[i+1] - item)
    
    # Estimate the delta t per data tupple
    delta_t = numpy.mean(diff) / (N/nfifo)
    
    # Defines the time for each tupple
    t = numpy.arange(times[0] - ((N/nfifo))*delta_t, times[-1]+delta_t, delta_t).tolist()
    
    return t


def parser_json(payload):
    '''
    Parser payload from mqtt
    Format json 
    Returns:
        device_id
        cloud_t
        traces 
        sr 
    where:
    traces =  {"t" : numpy.array(t), "x" : numpy.array(x), "y" : numpy.array(y), "z" : numpy.array(z)}
    
    '''
    payload = json.loads(payload)
    device_id = payload["device_id"]
    cloud_t = payload["cloud_t"]
    
    _x = []
    _y = []
    _z = []
    _t = []
    
    for i, item in enumerate(payload["traces"]):
        _x.append(item["x"])
        _y.append(item["y"])
        _z.append(item["z"])
        _t.append(item["t"])
        sr = item["sr"]
    
    x = [item for sublist in _x for item in sublist]
    y = [item for sublist in _y for item in sublist]
    z = [item for sublist in _z for item in sublist]
    
    # Set times per each data tupple (x, y and z)
    t = set_time(_t, sr, len(x))
    
    #traces = {"t" : numpy.array(t), "x" : numpy.array(x), "y" : numpy.array(y), "z" : numpy.array(z)}
    traces = {"t" : t, "x" : x, "y" : y, "z" : z}
    
    return device_id, cloud_t, traces, sr


def on_connect(client, userdata, flags, rc):
    #print("Connected with result code "+str(rc))
    client.subscribe("/traces")



def on_message(client, userdata, msg):
    
    m_decode = str(msg.payload.decode("utf-8","ignore"))
    m_in = json.loads(m_decode)
    
    # appending msg 
    # Missing check if the msgs are from different sensors
    inbox.append(m_in)
    #print(len(inbox))

    # When the msgs are more or equal than the long window
    if len(inbox) >= long_window:
        # Empty variables for the last 10 seconds
        _x = []
        _y = []
        _z = []
        _t = []
        # Looping over the inbox elements
        for i, item in enumerate(inbox):
            device_id, cloud_t, traces, sr = parser_json(item)
            #print(i, device_id)

            _x.extend(traces["x"])
            _y.extend(traces["y"])
            _z.extend(traces["z"])
            _t.extend(traces["t"])
        
        print("Device id:", device_id)

        # -------------- MOVING WINDOW -----------------------------
        # Select the last seconds and rename
        n = len(traces["x"])
        x = _x[-n*long_window:]
        y = _y[-n*long_window:]
        z = _z[-n*long_window:]
        t = _t[-n*long_window:]
        #print("Longitude:", len(x), len(y), len(z), len(t))
        
        # -------------- TRIGGER SECTION -----------------------------
        # STA / LTA algorithm
        x_sta_lta = sta_lta(numpy.array(x), short_window*n, long_window*n)
        y_sta_lta = sta_lta(numpy.array(y), short_window*n, long_window*n)
        z_sta_lta = sta_lta(numpy.array(z), short_window*n, long_window*n)

        
        # Estimating trigger times given a trigger level
        ttimes_x = trigger_time(x_sta_lta, numpy.array(t), trigger_level)
        ttimes_y = trigger_time(y_sta_lta, numpy.array(t), trigger_level)
        ttimes_z = trigger_time(z_sta_lta, numpy.array(t), trigger_level)

        # -------------- CHARACTERIZATION SECTION -----------------------------
        nttimes = len(ttimes_x) + len(ttimes_y) + len(ttimes_z) 
        if nttimes > 0:
            print("------------> Trigger of %s components. Sensor %s. Time %s" % (nttimes, device_id, cloud_t))
            accel = accel_value(numpy.array(x), numpy.array(y), numpy.array(z))
            pga = numpy.round(numpy.max(accel),3)
            print("Acceleration: ", pga)

            # --------------PUBLISH SECTION -----------------------------
            data_out = {"device_id" : numpy.str(device_id),"time" : numpy.str(cloud_t), "pga" : numpy.str(pga)}
            # topic
            topic = "/pga-trigger"
            host = "localhost"  
            port = 1883  
            client=mqtt.Client()
            client.connect(host, port)
            client.loop_start()
            print("Sending trigger data")
            client.publish(topic, data_out)


# --------------MQTT SECTION ----------------------------- 
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883)
#client.loop_forever()
client.loop_start()

print('init')

# Continue loop 
while True: 
    if len(inbox) <= long_window:
        continue
    else: 
        inbox = inbox[-long_window:]


client.disconnect()
client.loop_stop()