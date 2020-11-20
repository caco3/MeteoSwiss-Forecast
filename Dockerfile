FROM python:3

WORKDIR /

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CMD [ "python", "meteoswiss-forecast.py", "-z", "8001", "-f", "data/myForecast.png", "-v" ]

EXPOSE 8080
CMD ["python3", "webserver.py"]
