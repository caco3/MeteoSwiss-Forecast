# MeteoSwiss-Forecast
Script to fetch the MeteoSwiss Weather Forecast data and generate a graph


## Preparations

### Get Symbols
The symbols used by MeteoSwiss are provided as SVG files. How ever we need them as PNG files, preferably with a transparent background.
Due to copyright concerns, I do not want to provide the converted files here, instead, download and convert them yourself:
```
mkdir symbols
cd symbols
for i in {1..35}; do wget https://www.meteoschweiz.admin.ch/etc/designs/meteoswiss/assets/images/icons/meteo/weather-symbols/$i.svg; done
for i in {100..135}; do wget https://www.meteoschweiz.admin.ch/etc/designs/meteoswiss/assets/images/icons/meteo/weather-symbols/$i.svg; done
for f in *.svg; do convert -background transparent $f ${f%.svg}.png; done
rm *.svg
```
