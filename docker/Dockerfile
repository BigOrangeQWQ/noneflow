FROM python:3.10

WORKDIR /tmp

COPY ./noxfile.py /tmp/noxfile.py

# 更新软件包列表，安装git
RUN apt-get update \
    && apt-get install -y git \
    && apt-get install -y curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl https://pyenv.run | bash

ENV PYENV_ROOT="/root/.pyenv"
ENV PATH="${PATH}:/root/.pyenv/bin"

RUN eval "$(pyenv init -)" \
    && pyenv install 3.9 \
    && pyenv install 3.10 \
    && pyenv install 3.11 \
    && pyenv install 3.12 \
    && pyenv global 3.10

RUN pip install nox

RUN curl -sSL https://install.python-poetry.org -o install-poetry.py

RUN python install-poetry.py --yes

ENV PATH="${PATH}:/root/.local/bin"

CMD ["nox"]
