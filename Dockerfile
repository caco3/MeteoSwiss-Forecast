FROM python:3

WORKDIR /


COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


RUN apt-get update && \
    apt-get install -y \
        locales && \
    rm -r /var/lib/apt/lists/*

RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i -e 's/# de_DE.UTF-8 UTF-8/de_DE.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales

    
COPY . .


EXPOSE 80
CMD ["python3", "webserver.py"]
