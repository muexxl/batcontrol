FROM alpine:3.20

# add required libraries as py3-* Alpine packages 
# (this is equivalent to doing 
# pip install -r requirements.txt )
# the dependencies here need to reflect what batcontrol depends on
RUN apk add --no-cache \
            python3 \
            py3-numpy \
            py3-pandas\
            py3-yaml\
            py3-requests\
            py3-paho-mqtt

COPY ./ /batcontrol
WORKDIR /batcontrol
RUN ln -s /data/options.json /batcontrol/config/batcontrol_config.yaml

CMD [ "./batcontrol.py" ]