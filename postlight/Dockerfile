FROM node:24.10.0
WORKDIR /app
ADD https://github.com/postlight/parser-api-express/archive/refs/heads/master.tar.gz /app/
RUN tar xzvf master.tar.gz && \
mv parser-api-express-master/* . && \
npm install && \
npm update
EXPOSE 3000
CMD ["npm", "start", "--host", "0.0.0.0"]
