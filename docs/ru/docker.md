# Установка Docker и Docker Compose

1. Установите дополнительные пакеты:
    ```bash
    sudo apt install curl software-properties-common ca-certificates apt-transport-https -y
    ```
2. Импортируйте GPG-ключ Docker:
    ```bash
    wget -O- https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor | sudo tee /etc/apt/keyrings/docker.gpg > /dev/null
    ```
3. Добавьте репозиторий Docker:
    ```bash
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable"| sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    ```
4. Обновите индекс пакетов:
    ```bash
    sudo apt update
    ```
5. Установите Docker:
    ```bash
    sudo apt install docker-ce -y
    ```
6. Установите Docker Compose:
    ```bash
    sudo apt install docker-compose -y
    ```