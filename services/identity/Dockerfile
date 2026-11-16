FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS app

WORKDIR /app
# No generar __pycache__ en runtime: evita artefactos root (p. ej. tras
# `compose run --user 0:0`) que rompen ruff format --check del runner aislado.
ENV PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic_negocio ./alembic_negocio
COPY alembic_negocio.ini .
COPY scripts ./scripts
COPY alembic.ini .

RUN groupadd --gid 10001 identity \
    && useradd --uid 10001 --gid identity --no-create-home --shell /usr/sbin/nologin identity \
    && mkdir -p /app/data/fotos \
    && chown -R identity:identity /app/data

FROM app AS test

USER root
COPY requirements-dev.txt requirements-deploy.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests

USER 10001:10001

FROM app AS runtime-files

# El servicio no instala paquetes en ejecución. Retirar el toolchain evita
# conservar pip/setuptools y sus dependencias vendorizadas en producción.
RUN pip uninstall --yes pip setuptools wheel \
    && rm -rf /root/.cache /tmp/*

# Copiar el filesystem final a scratch aplana las capas de la imagen oficial.
# Así el artefacto desplegable tampoco conserva metadatos vulnerables borrados
# de las capas base, que los escáneres de cadena de suministro aún detectan.
FROM scratch AS runtime

COPY --from=runtime-files / /

WORKDIR /app
USER 10001:10001

EXPOSE 8080 8081
CMD ["sh", "/app/scripts/entrypoint.sh"]

FROM runtime AS production
