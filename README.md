<div align="center">

# 🔄 Kerio Updates Mirror

### Local update mirror for Kerio Control and Kerio Connect products

![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=flat&logo=docker&logoColor=white)
![Kerio](https://img.shields.io/badge/Kerio-Connect_&_Control-0078D4?style=flat)
![Telegram](https://img.shields.io/badge/Telegram-Channel-2CA5E0?style=flat&logo=telegram&logoColor=white)

**English** · [Русский](./docs/ru/README.ru.md)
</div>

## 🌐 Community & Support

Join our Telegram channel for updates, announcements, and community support:
[![Telegram](https://img.shields.io/badge/Join-Telegram_Channel-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/kerio_updates_mirror)

## 📋 Overview

**Kerio Updates Mirror** is a solution for local caching and mirroring of updates for Kerio Control and Kerio Connect
products, which allows you to:

- Reduce internet traffic and speed up the update process
- Provide updates for isolated networks or systems with limited internet access
- Automatically download and update antivirus databases, IPS/IDS Snort databases, and other security components

## ✅ Tested Configurations

| Component     | Version     |
|---------------|-------------|
| Ubuntu        | 24.04.1     |
| Kerio Connect | 10.0.6.8504 |
| Kerio Control | 9.4.5.8526  |

## 🚀 Installation and Setup

### Prerequisites

- Docker and Docker Compose ([installation guide](./docs/en/docker.md))

### Option 1: Running from pre-built Docker images (recommended)

1. [Download Docker images](https://t.me/my_store_files_bot?start=kerio-updates-mirror)
2. Load images from archives:
   ```bash
   sudo docker load -i tor_v1.1.2.tar
   sudo docker load -i mirror_v1.2.0.tar
   ```
3. Download or clone the repository:
   ```bash
   git clone https://github.com/cnekTep/kerio-updates-mirror.git
   cd kerio-updates-mirror
   ```
4. Make necessary configurations
5. Start the containers:
   ```bash
   sudo docker-compose up -d
   ```

### Option 2: Building from source code

1. Download or clone the repository:
   ```bash
   git clone https://github.com/cnekTep/kerio-updates-mirror.git
   cd kerio-updates-mirror
   ```
2. Make necessary configurations
3. Start building and deploying containers:
   ```bash
   sudo docker-compose up -d
   ```

### Option 3: Importing a Ready-to-Use Virtual Machine

This option provides a fully configured out-of-the-box solution, ideal for quick deployment.

1. [Download the Virtual Machine](https://t.me/my_store_files_bot?start=kerio-updates-mirror)
2. Import the image into your virtualization system (Hyper-V, VMWare - OVF Template)
3. Start the virtual machine

<details>
<summary>📝 Hyper-V Import Instructions</summary>

1. Open **Hyper-V Manager**
2. In the **Action** menu, select **New** → **Virtual Machine**
3. In the creation wizard:
    - Enter a name for the virtual machine (for example, "Kerio Updates Mirror")
    - If needed, change the VM file location
    - Click **Next**
4. **Important**: In the generation selection section, choose **Generation 1**
5. Specify the amount of RAM (512-1024 MB recommended)
6. Configure network connection (select an existing virtual switch)
7. At the virtual hard disk configuration step:
    - Select **Use an existing virtual hard disk**
    - Click **Browse** and specify the path to the downloaded `.vhdx` file
    - Click **Next**
8. Review the parameter summary and click **Finish**

</details>

<details>
<summary>📝 VMware Import Instructions</summary>

#### Step-by-step import instructions for VMware Workstation/Player

1. Launch VMware Workstation or VMware Player
2. Select **File** → **Open**
3. Find and select the `.ovf` file from the unpacked archive
4. In the import dialog:
    - Specify the virtual machine name (for example, "Kerio Updates Mirror")
    - If needed, change the virtual machine location
    - Click **Import**
5. Wait for the import process to complete

#### Step-by-step import instructions for VMware ESXi

1. Log in to the VMware ESXi or vSphere web interface
2. Navigate to the **Virtual Machines** section
3. Click **Create/Register Virtual Machine**
4. Select **Deploy a virtual machine from OVF or OVA file**
5. Specify the virtual machine name
6. Drag and drop the OVF and VMDK files to the upload area or use the file selection button
7. Select storage for the VM placement
8. Select a network for connection
9. Click **Next** and then **Finish**

</details>

<details>
<summary>📝 Virtual Machine Specifications and Setup</summary>

#### Technical Specifications

- **Operating System**: Debian 12 (minimal installation)
- **Resource Requirements**: 512-1024 MB RAM, 1 CPU, 10 GB storage
- **Pre-installed Software**: SSH, Midnight Commander, htop, Docker, Docker Compose
- **Docker Containers**: Portainer, Kerio Updates Mirror

#### System Access

- **Default Credentials**:
    - Username: `root`
    - Password: `root`

#### Initial Setup

1. Connect to the virtual machine via SSH (port 22)
2. **Strongly recommended** to change the root password:
   ```bash
   passwd
   ```
3. Configure the correct timezone:
   ```bash
   dpkg-reconfigure tzdata
   ```
4. Check the current IP address (DHCP is used by default):
   ```bash
   ip a
   ```

#### Network Configuration

To change network parameters:

1. Edit network interfaces:
   ```bash
   nano /etc/network/interfaces
   # or
   mc # then navigate to /etc/network/interfaces
   ```
2. Configure DNS servers:
   ```bash
   nano /etc/resolv.conf
   # or 
   mc # then navigate to /etc/resolv.conf
   ```

#### Management via Portainer

The virtual machine includes pre-installed Portainer for convenient Docker container management:

- **URL**: `https://VIRTUAL_MACHINE_IP:9443`
- **Credentials**:
    - Username: `admin`
    - Password: `admin`

> **Note**: It is recommended to change the Portainer admin password after first login.

</details>

## ⚙️ Configuring Kerio Products

### Kerio Connect

To configure updates through the local mirror in Kerio Connect, you need to specify an HTTP proxy server in the
settings:

<details>
<summary>Kerio Connect Configuration (click to expand)</summary>

#### For Linux server with Kerio Connect and Docker containers on the same server:

1. Go to **Configuration → Advanced Options → HTTP Proxy**
2. Specify:
    - **Address**: 172.222.0.5
    - **Port**: 8118

#### For Windows or distributed infrastructure:

> Server runs on Windows or a distributed infrastructure is used (Kerio Connect and Docker containers are located on
> different servers)

1. Go to **Configuration → Advanced Options → HTTP Proxy**
2. Specify:
    - **Address**: IP_address_of_server_with_Docker_containers
    - **Port**: 8118

</details>

### Kerio Control

To configure updates through the local mirror in Kerio Control, you need to add DNS records:

<details>
<summary>Kerio Control Configuration (click to expand)</summary>

1. Go to **Configuration → DNS → Local DNS Lookup**
2. Add the following records (where Update_server_IP is the IP address of the server with the mirror):

| IP Address       | Hostname                | Description          |
|------------------|-------------------------|----------------------|
| Update_server_IP | bda-update.kerio.com    | kerio-updates-mirror |
| Update_server_IP | bdupdate.kerio.com      | kerio-updates-mirror |
| Update_server_IP | ids-update.kerio.com    | kerio-updates-mirror |
| Update_server_IP | prod-update.kerio.com   | kerio-updates-mirror |
| Update_server_IP | update.kerio.com        | kerio-updates-mirror |
| Update_server_IP | wf-activation.kerio.com | kerio-updates-mirror |

</details>

## 📊 Features

- **For Kerio Connect**:
    - Automatic downloading of antivirus databases when accessing the mirror
    - Support for anti-spam functionality

- **For Kerio Control**:
    - Automatic downloading of antivirus databases when accessing the mirror
    - Scheduled updates for:
        - IPS/IDS Snort databases
        - GeoIP databases
        - Lists of compromised addresses
    - Ability to retrieve GeoIP databases from external sources on the GitHub platform

## 🔧 Advanced Settings

### TOR Bridge Configuration

TOR bridges are used to ensure reliable access to updates even in case of access restrictions:

- TOR bridges configuration file: `_tor/config/bridges.config`
- When the `USE_CHECK_TOR=true` parameter is enabled in `docker-compose.yml`, the system automatically checks internet
  accessibility through TOR and updates bridges if necessary
- New bridges can be obtained from the [official website](https://bridges.torproject.org) or
  via [Telegram bot](https://t.me/GetBridgesBot)

### Monitoring and Management

- Access to the web management interface, depending on the settings in docker-compose.yml:
    - Only port 9980 is published and only Kerio Connect is updated: `http://SERVER_IP:9980`
    - Ports 80, 443 are published and Kerio Control is updated: `http://SERVER_IP:80`