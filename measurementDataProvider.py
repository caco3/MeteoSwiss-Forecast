import json 
from influxdb import InfluxDBClient
import numpy as np
import datetime


"""
Fetches the measured data from the InfluxDB.
The data of the InfluxDB gets filled by Homeassistant.
"""
class MeasurementDataProvider():
    
    def __init__(self, measurementDataDbHost, measurementDataDbPort, measurementDataDbUser, measurementDataDbPassword):
        self.measurementDataDbHost = measurementDataDbHost
        self.measurementDataDbPort = measurementDataDbPort
        self.measurementDataDbUser = measurementDataDbUser
        self.measurementDataDbPassword = measurementDataDbPassword
    
    
    def getMeasurement(self, sensor, groupingInterval=10, fill=0):
        print("Fetching data of sensor %r from InfluxDB..." % sensor)
        client = InfluxDBClient(host=self.measurementDataDbHost, port=self.measurementDataDbPort, username=self.measurementDataDbUser, password=self.measurementDataDbPassword)
        client.get_list_database()
        
        query = 'SELECT MEAN("value") FROM "homeassistant"."autogen"."sensor.' + sensor + '" WHERE time > now() - 24h GROUP BY time(' + str(groupingInterval) + 'm) FILL(' + str(fill) + ')'
        #query = 'SELECT MEAN("value") FROM "homeassistant"."autogen"."sensor.' + sensor + '" WHERE time > now() - 48h GROUP BY time(' + str(groupingInterval) + 'm) FILL(' + str(fill) + ')' # test
        
        #print(query)

        #result = client.query('SELECT MEAN("value") FROM "homeassistant"."autogen"."sensor.regenstaerke" WHERE time > now() - 12h GROUP BY time(10m) FILL(0)')
        result = client.query(query)
        
        #print(result)
        
        if str(result) == "ResultSet({})":
            print("No data in Influx-DB!")
            return None

        res = result.raw['series'][0]['values']
        time, data = np.transpose(res)

        time = [int(datetime.datetime.strptime(x, '%Y-%m-%dT%H:%M:%SZ').timestamp()) for x in time]
        #time = [int(datetime.datetime.strptime(x, '%Y-%m-%dT%H:%M:%SZ').timestamp()) + 24*3600 for x in time] # test
        
        data = list(data)
        
        #print(sensor, data)
        #data = [float(x) for x in data]
        
        for i in range(len(data)):
            try:
                data[i] = float(data[i])
            except:
                data[i] = 0
        
        #print(sensor, data)
        

        return (time, data)
