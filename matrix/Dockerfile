FROM matrixdotorg/synapse:v1.153.0

USER root

COPY docker/matrix/render_config.py /nexus/render_config.py
COPY docker/matrix/start.sh /nexus/start.sh
# Windows checkouts can carry CRLF into shell scripts; normalize it in-image.
RUN sed -i 's/\r$//' /nexus/start.sh && chmod 0755 /nexus/start.sh

ENTRYPOINT ["/nexus/start.sh"]
