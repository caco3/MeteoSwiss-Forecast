#!/usr/bin/python
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlparse, parse_qs
from meteoswissForecast import MeteoSwissForecast
from markGraphic import markGraphic
import logging
import os
import json


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


# This class will handle any incoming request from
# a browser 
class myHandler(BaseHTTPRequestHandler):
    # Handler for the GET requests
    def do_GET(self):
        self.send_response(200)        
        
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        
        print("File: %s, query: %s" % (parsed_url.path, query), flush=True)
        
        if parsed_url.path == "/generate-forecast":
            self.generate(query)
        elif parsed_url.path == "/get-forecast":
            self.returnMarkedImage(query)
        elif parsed_url.path == "/get-metadata":
            self.returnMetaData(query)
        elif parsed_url.path == "/":
            self.showHelp(False)
        else:
            self.showHelp(True)

        
    def showHelp(self, invalid=True):
        print("Showing help")
        self.send_header('Content-type','text/html')
        self.end_headers()
        
        self.wfile.write(b"<h1>Meteoswiss Forecast Generator</h1>\n")
        
        if invalid:
            self.wfile.write(b"<span style=\"color: red\">Invalid call!</span><br><br><hr><br>\n")
        
        self.wfile.write(b"The generation of the forcast takes a moment. Because of this, it is a two-step-process:<br>1. Generate a forecast for a Zip Code using the wanted configuration. This has only to be done once an hour, MeteoSwiss only re-runs the model every few hours.<br>2. Download the forecast as many times as you want, applying the same zip code and optionally a time mark.<br>\n")                
        self.wfile.write(b"Since every generated forecast is linked to its zip code, forecasts for differen cities can be provided at the same time.<br>\n")
        
        self.wfile.write(b"<h2>Generate</h2>\n")
        url = "generate-forecast?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>"
        self.wfile.write(bytes(link, 'utf-8'))
        
        self.wfile.write(b"<h3>Note</h3>\n")
        self.wfile.write(b"Depending on the number of days to show, this will take several seconds!\n")
        
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"<tr><td><b>days-to-show:</b></td></td><td>Number of days to show (1..8).</td><td>Optional, default: 8</td></tr>\n")
        self.wfile.write(b"<tr><td><b>height:</b></td><td>Height of the graph in pixel.</td><td>Optional, default: 300</td></tr>\n")
        self.wfile.write(b"<tr><td><b>width:</b></td><td>Width of the graph in pixel.</td><td>Optional, default: 1920</td></tr>\n")
        self.wfile.write(b"<tr><td><b>time-divisions:</b></td><td>Distance in hours between time labels.</td><td>Optional, default: 6</td></tr>\n")
        self.wfile.write(b"<tr><td><b>use-dark-mode:</b></td><td>Use dark colors.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>font-size:</b></td><td>Font Size in pixel.</td><td>Optional, default: 12</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-min-max-temperatures:</b></td><td>Show min/max temperature per day.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-rain-variance:</b></td><td>Show rain variance.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>locale:</b></td><td>Used localization of the date, eg. en_US.utf8.</td><td>Optional, default: en_US.utf8</td></tr>\n")
        self.wfile.write(b"<tr><td><b>date-format:</b></td><td>Format of the dates, eg. \"%%A, %%-d. %%B\", see https://strftime.org/ for details'.</td><td>Optional, default: %A, %-d. %B</td></tr>\n")
        self.wfile.write(b"<tr><td><b>time-format:</b></td><td>Format of the times, eg. \"%%H:%%M\", see https://strftime.org/ for details'.</td><td>Optional, default: %H:%M</td></tr>\n")
        self.wfile.write(b"<tr><td><b>symbol-zoom:</b></td><td>Scaling of the symbols.</td><td>Optional, default: 1.0</td></tr>\n")
        self.wfile.write(b"<tr><td><b>symbol-divisions:</b></td><td>Only draw every x symbol (1 equals every 3 hours).</td><td>Optional, default: 1</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-city-name:</b></td><td>Show the name of the city.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"</table>\n")
        
        self.wfile.write(b"<h3>Example</h3>\n")
        url = "generate-forecast?zip-code=8001&time-format=%H&time-divisions=3&height=250&width=600&days-to-show=4&show-min-max-temperatures=true&font-size=12&locale=de_DE.utf8&symbol-zoom=0.8&show-rain-variance=true"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
    
    
        self.wfile.write(b"<h2>Get Forecast Image</h2>\n")
        url = "get-forecast?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"<tr><td><b>mark-time:</b></td><td>Add a mark of the current time.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"</table>\n")

        self.wfile.write(b"<h3>Example</h3>\n")
        url = "get-forecast?zip-code=8001&mark-time=1"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))


        self.wfile.write(b"<h2>Get Forecast Metadata</h2>\n")
        url = "get-metadata?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"</table>\n")

    
    def getForecastImage(self, query):
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
        
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return
        
        self.send_header('Content-type','image/png')
        self.end_headers()
        try:
            f = open(forecastFile + str(zipCode) + ".png", 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
    
    
    def returnMarkedImage(self, query):
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
        
            if 'mark-time' in query:
                markTime = str2bool(query['mark-time'][0])
            else:
                markTime = False
        
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return
        
        
        if markTime:
            try:
                with open(metaDataFile + str(zipCode) + ".json") as metaFile:
                    metaData = json.load(metaFile)
            except Exception as e:
                self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
                return

            print(metaData)
            markGraphic(inputFile=forecastFile + str(zipCode) + ".png", 
                        outputFile=markedForecastFile + str(zipCode) + ".png", 
                        metaFile=metaDataFile + str(zipCode) + ".json", x=metaData['firstDayX'], y=metaData['firstDayY'],
                        w=metaData['dayWidth'], h=metaData['dayHeight'], fakeTime=False, test=False)

        self.send_header('Content-type','image/png')
        self.end_headers()
        try:
            if markTime:
                filename = markedForecastFile + str(zipCode) + ".png"
            else:
                filename = forecastFile + str(zipCode) + ".png"
            print("Sending %s" % filename)
            f = open(filename, 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
    
    
    def returnMetaData(self, query):
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
        
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return
        
        self.send_header('Content-type','application/json')
        self.end_headers()
        try:
            f = open(metaDataFile + str(zipCode) + ".json", 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            
            
    def generate(self, query):
        logLevel = logging.INFO
                
        # TODO return json with result info
        self.send_header('Content-type','text/html')
        self.end_headers()
        
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
                
            if 'days-to-show' in query:
                daysToShow = int(query['days-to-show'][0])
                if daysToShow < 1 or daysToShow > 8:
                    self.wfile.write(bytes("days-to-show must be 1..8!"))
                    return
            else:
                daysToShow = 2
                    
            if 'height' in query:
                height = int(query['height'][0])
            else:
                height = 300
                    
            if 'width' in query:
                width = int(query['width'][0])
            else:
                width = 1920
                    
            if 'time-divisions' in query:
                timeDivisions = int(query['time-divisions'][0])
            else:
                timeDivisions = 6
                    
            if 'use-dark-mode' in query:
                darkMode = str2bool(query['use-dark-mode'][0])
            else:
                darkMode = False
                    
            if 'font-size' in query:
                fontSize = int(query['font-size'][0])
            else:
                fontSize = 12

            if 'show-min-max-temperatures' in query:
                minMaxTemperatures = str2bool(query['show-min-max-temperatures'][0])
            else:
                minMaxTemperatures = False
            
            if 'show-rain-variance' in query:
                rainVariance = str2bool(query['show-rain-variance'][0])
            else:
                rainVariance = False
            
            if 'locale' in query:
                locale = query['locale'][0]
            else:
                locale = "en_US.utf8"
            
            if 'date-format' in query:
                dateFormat = query['date-format'][0]
            else:
                dateFormat = "%A, %-d. %B"
            
            if 'time-format' in query:
                timeFormat = query['time-format'][0]
            else:
                timeFormat = "%H:%M"
            
            if 'symbol-zoom' in query:
                symbolZoom = float(query['symbol-zoom'][0])
            else:
                symbolZoom = 1.0
            
            if 'symbol-divisions' in query:
                symbolDivisions = int(query['symbol-divisions'][0])
            else:
                symbolDivisions = 1
            
            if 'show-city-name' in query:
                cityName = str2bool(query['show-city-name'][0])
            else:
                cityName = False
            
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return

            
        self.wfile.write(b"Parameters ok<br>\n")
        self.wfile.flush()
        print("Parameters ok", flush=True)
            
        logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)
        logging.getLogger("matplotlib").setLevel(logging.WARNING) # hiding the debug messages from the matplotlib

        self.wfile.write(b"Feching data for %d...<br>\n" % zipCode)
        self.wfile.flush()
        print("Fetching data for %d..." % zipCode, flush=True)

        try:
            meteoSwissForecast = MeteoSwissForecast(zipCode)      
        except Exception as e:
            print(e)
            if "404" in str(e):
                self.wfile.write(b"Unknown Zip Code!")
            else:
                self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))            
            return

        dataUrl = meteoSwissForecast.getDataUrl()
        print("Data URL: %s" % dataUrl, flush=True)

        self.wfile.write(b"Generating Forecast...<br>\n")
        self.wfile.flush()
        print("Generating Forecast...", flush=True)
        
        forecastData = meteoSwissForecast.collectData(dataUrl=dataUrl, daysToUse=daysToShow, timeFormat=timeFormat, dateFormat=dateFormat, localeAlias=locale)
        meteoSwissForecast.generateGraph(data=forecastData, outputFilename=(forecastFile + str(zipCode) + ".png"), timeDivisions=timeDivisions, graphWidth=width, graphHeight=height, darkMode=darkMode, rainVariance=rainVariance, minMaxTemperature=minMaxTemperatures, fontSize=fontSize, symbolZoom=symbolZoom, symbolDivision=symbolDivisions, showCityName=cityName, writeMetaData=(metaDataFile + str(zipCode) + ".json"))
        
        print("Image got saved as " + forecastFile + str(zipCode) + ".png")
        print("Metadata got saved as " + metaDataFile + str(zipCode) + ".json")

        self.wfile.write(b"Done<br>\n")
        print("Done", flush=True)       
        
        url = "get-forecast?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a><br>\n"
        self.wfile.write(bytes("You can now download the Forecast Image from " + link, 'utf-8'))

        url = "get-forecast?zip-code=8001&mark-time=1"
        link = "<a href=\"" + url + "\">" + url + "</a><br>\n"
        self.wfile.write(bytes("Or use the following link which additionally adds a mark of the current time: " + link, 'utf-8'))
    
        return


try:
    forecastFile = "./data/forecast_"
    markedForecastFile = "./data/markedForecast_"
    metaDataFile = "./data/metadata_"

    internalPort = 80
    #internalPort = 12081 # testing
    
    try:
        if not os.path.exists("./data"):
            os.makedirs("./data")
    except OSError:
        print ("Failed to create data folder")
except Exception as e:
    print("An error occurred: %s" % e)
    exit(1)

# Run the service
try:
    server = HTTPServer(('', internalPort), myHandler)
    print("Meteoswiss Forecast Generator")
    print("Copyright (c) 2020 by George Ruinelli <george@ruinelli.ch>, https://github.com/caco3/MeteoSwiss-Forecast")
    
    print("Ready to receive requests")

    # Wait forever for incoming http requests
    server.serve_forever()

except KeyboardInterrupt:
    print ('^C received, shutting down the web server')
    server.socket.close()

