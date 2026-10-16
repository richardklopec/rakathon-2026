# InterSystems IRIS for Health Community + empty FHIR R4 server (no sample data).
# Adapted from intersystems-community/FHIR-AI-Hackathon-Kit (MIT), see PREEXISTING.md.
FROM intersystems/irishealth-community:latest-cd

# data volume (ISC_DATA_DIRECTORY) must exist and be owned by irisowner, otherwise IRIS cannot start
USER root
RUN mkdir -p /durable && chown irisowner:irisowner /durable

USER irisowner
COPY --chown=irisowner:irisowner merge.cpf /tmp/merge.cpf

# enable %Service_CallIn (Python native API) and un-expire dev passwords
RUN iris start IRIS && \
    iris merge IRIS /tmp/merge.cpf && \
    echo 'do ##class(Security.Users).UnExpireUserPasswords("*")' | iris session IRIS -U %SYS && \
    iris stop IRIS quietly
