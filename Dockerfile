# start by pulling the python image
FROM python:3.13-slim

# copy the requirements file into the image
COPY ./code/requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
RUN pip install -U pip setuptools wheel
RUN pip install -r requirements.txt

# copy every content from the local file to the image
COPY ./code/ /app

ENV KOSYNC_SQLITE3_DB=/data/sqlite3.db
CMD ["gunicorn", "-b", "0.0.0.0:8081", "wbip_wrapper:app"]
#ENTRYPOINT ["python"]
#CMD ["./wbip_wrapper.py"]

