# Installing Docker and Docker Compose

1. Install additional packages:
    ```bash
    sudo apt install curl software-properties-common ca-certificates apt-transport-https -y
    ```
2. Import the Docker GPG key:
    ```bash
    wget -O- https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor | sudo tee /etc/apt/keyrings/docker.gpg > /dev/null
    ```
3. Add a Docker repository:
    ```bash
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable"| sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    ```
4. Update the package index:
    ```bash
    sudo apt update
    ```
5. Install Docker:
    ```bash
    sudo apt install docker-ce -y
    ```
6. Install Docker Compose:
    ```bash
    sudo apt install docker-compose -y
    ```
