# start by pulling the python image
FROM python:3.11-slim

# copy the requirements file into the image
COPY ./code/requirements.txt /app/requirements.txt

# switch working directory
WORKDIR /app

# install the dependencies and packages in the requirements file
RUN pip install -r requirements.txt

# copy every content from the local file to the image
COPY ./code/ /app

ENV KOSYNC_SQLITE3_DB=/data/sqlite3.db

# configure the container to run in an executed manner
ENTRYPOINT [ "python" ]

CMD ["wbip_wrapper.py" ]

