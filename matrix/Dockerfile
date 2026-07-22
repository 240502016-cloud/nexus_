FROM matrixdotorg/synapse:v1.153.0

USER root

COPY docker/matrix/render_config.py /nexus/render_config.py
COPY docker/matrix/start.sh /nexus/start.sh
RUN chmod 0755 /nexus/start.sh

ENTRYPOINT ["/nexus/start.sh"]

