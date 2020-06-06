from urllib.request import Request, urlopen
import json
import pprint
import time
import datetime
import matplotlib.pyplot as plt
import numpy as np
import math

domain = "https://www.meteoschweiz.admin.ch"
indexPage = "home.html?tab=overview"

dataFilePrefix = "/product/output/forecast-chart/version__"
dataFileSuffix = ".json"

# Get offset from local time to UTC, see also https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
ts = time.time()
utcOffset = (datetime.datetime.fromtimestamp(ts) -
              datetime.datetime.utcfromtimestamp(ts)).total_seconds()
utcOffset = int(utcOffset / 3600) # in hours
#print("UTC offset:", utcOffset)


"""
gets the data URL
Example Data URL: https://www.meteoschweiz.admin.ch//product/output/forecast-chart/version__20200605_1122/de/800100.json
The 8001 represents the Zip Code of the location you want
"""
def getDataUrl(zipCode, domain, indexPage, dataFilePrefix, dataFileSuffix):
    req = Request(domain + "/" + indexPage, headers={'User-Agent': 'Mozilla/5.0'})
    indexPage = str(urlopen(req).read())

    dataUrlStartPosition = indexPage.find(dataFilePrefix)
    dataUrlEndPosition = indexPage.find(dataFileSuffix, dataUrlStartPosition)

    return domain + "/" + indexPage[dataUrlStartPosition:dataUrlEndPosition - 6] + zipCode + "00" + dataFileSuffix

def getForecastData(dataUrl):
    req = Request(dataUrl, headers={'User-Agent': 'Mozilla/5.0'})
    forcastDataPlain = (urlopen(req).read()).decode('utf-8')
    return json.loads(forcastDataPlain)
    
    
# normal
def dataExtractor1(forecastData, days, topic):
    topicData = []
    for day in range(0, days):
        for hour in range(0, 24):
            topicData.append(forecastData[day][topic][hour][1])
    return topicData

# Data is in sub-field "data"
def dataExtractor2(forecastData, days, topic):
    topicData = []
    for day in range(0, days):
        for hour in range(0, 24):
            topicData.append(forecastData[day][topic]["data"][hour][1])
    return topicData

# Data contains list of two (min/max) values
def dataExtractor3(forecastData, days, topic):
    topicDataMin = []
    topicDataMax = []
    for day in range(0, days):
        for hour in range(0, 24):
            topicDataMin.append(forecastData[day][topic][hour][1])
            topicDataMax.append(forecastData[day][topic][hour][2])
    return [topicDataMin, topicDataMax]
    
def extractForecastData(forecastData):    
    days = len(forecastData)

    dictionary = {}    
    dayNames = []  
    formatedTime = []
    timestamps = []
    rainfall = []
    
    for day in range(0, days):
        # get day names
        dayNames.append(forecastData[day]["day_string"]) # name of the day
        
        # get timestamps (the same for all data)
        for hour in range(0, 24):
            timestamp = forecastData[day]["rainfall"][hour][0]
            timestamp = int(int(timestamp) / 1000) + utcOffset * 3600
            timestamps.append(timestamp)
    
    dayIndex = 0
    for timestamp in timestamps:
        if timestamp % (24*3600) == 0: # midnight
            #formated = datetime.datetime.utcfromtimestamp(timestamp).strftime('%d. %b')
            formated = dayNames[dayIndex]
            dayIndex += 1
        else:
            formated = datetime.datetime.utcfromtimestamp(timestamp).strftime('%H:%M')
        #print(timestamp, formated)
        formatedTime.append(formated)
    
    rainfall = dataExtractor1(forecastData, days, "rainfall")
    sunshine = dataExtractor1(forecastData, days, "sunshine")
    temperature = dataExtractor1(forecastData, days, "temperature")
    rainfallVarianceMin, rainfallVarianceMax = dataExtractor3(forecastData, days, "variance_rain")
    temperatureVarianceMin, temperatureVarianceMax = dataExtractor3(forecastData, days, "variance_range")
    wind = dataExtractor2(forecastData, days, "wind")
    windGustPeak = dataExtractor2(forecastData, days, "wind_gust_peak")
        
    # todo also extract symbols
            
    dictionary["noOfDays"] = days
    dictionary["dayNames"] = dayNames
    dictionary["timestamps"] = timestamps
    dictionary["formatedTime"] = formatedTime
    dictionary["rainfall"] = rainfall
    dictionary["rainfallVarianceMin"] = rainfallVarianceMin
    dictionary["rainfallVarianceMax"] = rainfallVarianceMax
    dictionary["temperature"] = temperature
    dictionary["temperatureVarianceMin"] = temperatureVarianceMin
    dictionary["temperatureVarianceMax"] = temperatureVarianceMax
    dictionary["wind"] = wind
    dictionary["windGustPeak"] = windGustPeak

    
    return dictionary
    
    
    
def plotForecast(plotData):    
    fig, ax1 = plt.subplots()
    
    # Show gray background on every 2nd day 
    for day in range(0, plotData["noOfDays"], 2):
        plt.axvspan(plotData["timestamps"][0 + day * 24], plotData["timestamps"][23 + day * 24] + 3600, facecolor='gray', alpha=0.2)
    
    # Rain
    rainColorSteps = [1, 2, 4, 6, 10, 20, 40, 60, 100]
    rainColorStepSizes = [1, 1, 2, 2, 4, 10, 20, 20, 40]
    rainColors = ["#9d7d95", "#0001f9", "#088b2d", "#02ff07", "#70e900", "#feff01", "#ffc900", "#fe1a00", "#ac00e0"]
    rainBars = [0] * len(rainColorSteps)
    
    for i in range(0, len(rainColorSteps)):
        rainBars[i] = []
    
    for rain in plotData["rainfall"]:
        for i in range(0, len(rainColorSteps)):
            if rain > rainColorSteps[i]:
                rainBars[i].append(rainColorStepSizes[i])
            else:
                if i > 0:
                    rainBars[i].append(max(rain - rainColorSteps[i-1], 0))
                else:
                    rainBars[i].append(rain)
                continue
        
    ax1.bar(plotData["timestamps"], rainBars[0], width=3000, color=rainColors[0], align='edge')
    bottom = [0] * len(rainBars[0])
    for i in range(1, len(rainColorSteps)):
        bottom = np.add(bottom, rainBars[i-1]).tolist()
        ax1.bar(plotData["timestamps"], rainBars[i], bottom=bottom, width=3000, color=rainColors[i], align='edge')
    
    ax1.set_ylabel('Rainfall', color=rainColors[1])
    ax1.tick_params(axis='y', labelcolor=rainColors[1])
    
    plt.ylim(0, max(plotData["rainfall"]) + 1)
    
    
    # color bar as y axis (not working)
    #autoAxis = ax1.axis()
    ##rec = plt.Rectangle((autoAxis[0]-0.7,autoAxis[2]-0.2),(autoAxis[1]-autoAxis[0])+1,(autoAxis[3]-autoAxis[2])+0.4,fill=False,lw=2)
    #rec = plt.Rectangle((plotData["timestamps"][0] - 10000, 0),  10000, 1  , fill=False, lw=2)
    #rec = ax1.add_patch(rec)
    #rec.set_clip_on(False)
    
    
    
    
    # Temperature
    color = "red"
    ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
    ax2.plot(plotData["timestamps"], plotData["temperature"], label = "temperature", color=color, linewidth=4)
    ax2.set_ylabel('Temperature', color=color)
    ax2.tick_params(axis='y', labelcolor=color)
    
    plt.grid(True)
    
    # Make sure minimum temperature is 0 or lower
    # Make sure temperature max is multiple of 5
    plt.ylim(min(0, min(plotData["temperatureVarianceMin"])), math.ceil(float(max(plotData["temperatureVarianceMax"])) / 5) * 5)
    
    
    
    # Temperature variance
    color = "red"
    ax3 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
    
    ax3.fill_between(plotData["timestamps"], plotData["temperatureVarianceMin"], plotData["temperatureVarianceMax"], facecolor='red', alpha=0.2)
    ax3.tick_params(axis='y', labelcolor=color)
    
    plt.ylim(min(0, min(plotData["temperatureVarianceMin"])), math.ceil(float(max(plotData["temperatureVarianceMax"])) / 5) * 5)
    
      
    
    
    # General plot settings
    ax1.tick_params(axis='x', rotation=45)
        
    plt.xticks(plotData["timestamps"][::3], plotData["formatedTime"][::3])
    
    plt.margins(x=0)
    ax1.margins(x=0)
    ax2.margins(x=0)
    plt.subplots_adjust(left=0.0, right=2, top=0.9, bottom=0.1)
    
    plt.savefig('meteoswiss-forecast.png', bbox_inches='tight')
    
    
    

def main(zipCode, domain, indexPage, dataFilePrefix, dataFileSuffix):
    dataUrl = getDataUrl(zipCode, domain, indexPage, dataFilePrefix, dataFileSuffix)
    #print(dataUrl)
    
    forecastData = getForecastData(dataUrl)
    
    plotData = extractForecastData(forecastData)
    
    #pprint.pprint(plotData)

    plotForecast(plotData)
    
    
    

if __name__ == '__main__':
    zipCode = "8620" # Wetzikon
    #zipCode = "8400" # Winterthur
    main(zipCode, domain, indexPage, dataFilePrefix, dataFileSuffix)
    
